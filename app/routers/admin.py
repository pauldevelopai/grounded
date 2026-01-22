"""Admin routes for platform management."""
import os
import shutil
from datetime import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin
from app.models.auth import User
from app.models.toolkit import ToolkitDocument, ToolkitChunk, ChatLog, Feedback
from app.services.ingestion import ingest_document, reindex_document

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")

# Data directory for uploads (persistent filesystem)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin dashboard homepage with overview stats.
    """
    # Get overview stats
    user_count = db.query(func.count(User.id)).scalar()
    admin_count = db.query(func.count(User.id)).filter(User.is_admin == True).scalar()
    document_count = db.query(func.count(ToolkitDocument.id)).scalar()
    chunk_count = db.query(func.count(ToolkitChunk.id)).scalar()
    chat_count = db.query(func.count(ChatLog.id)).scalar()
    feedback_count = db.query(func.count(Feedback.id)).scalar()

    stats = {
        "users": user_count,
        "admins": admin_count,
        "documents": document_count,
        "chunks": chunk_count,
        "chats": chat_count,
        "feedbacks": feedback_count
    }

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "user": user, "stats": stats}
    )


# ============================================================================
# USER MANAGEMENT
# ============================================================================

@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all users with admin status.
    """
    users = db.query(User).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "user": user, "users": users}
    )


@router.post("/users/{user_id}/promote")
async def promote_user(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Promote a user to admin.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_user.is_admin = True
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/demote")
async def demote_user(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Demote a user from admin.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent demoting yourself
    if target_user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")

    target_user.is_admin = False
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=303)


# ============================================================================
# DOCUMENT MANAGEMENT
# ============================================================================

@router.get("/documents", response_class=HTMLResponse)
async def list_documents(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all ingested documents with chunk counts and timestamps.
    """
    # Get documents with chunk counts
    documents = (
        db.query(
            ToolkitDocument,
            func.count(ToolkitChunk.id).label("chunk_count")
        )
        .outerjoin(ToolkitChunk, ToolkitDocument.id == ToolkitChunk.document_id)
        .group_by(ToolkitDocument.id)
        .order_by(ToolkitDocument.upload_date.desc())
        .all()
    )

    # Format for template
    docs_with_counts = []
    for doc, count in documents:
        docs_with_counts.append({
            "id": str(doc.id),
            "version_tag": doc.version_tag,
            "source_filename": doc.source_filename,
            "file_path": doc.file_path,
            "upload_date": doc.upload_date,
            "chunk_count": count,
            "is_active": doc.is_active
        })

    return templates.TemplateResponse(
        "admin/documents.html",
        {"request": request, "user": user, "documents": docs_with_counts}
    )


@router.get("/documents/upload", response_class=HTMLResponse)
async def upload_document_page(
    request: Request,
    user: User = Depends(require_admin)
):
    """
    Document upload page.
    """
    return templates.TemplateResponse(
        "admin/upload.html",
        {"request": request, "user": user}
    )


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    version_tag: str = Form(...),
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Upload and ingest a new document.
    """
    # Validate file type
    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="File must be a .docx file")

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Create unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    # Save uploaded file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Ingest document
        doc = ingest_document(
            db=db,
            file_path=file_path,
            version_tag=version_tag,
            source_filename=file.filename,
            create_embeddings=create_embeddings
        )

        return RedirectResponse(url="/admin/documents", status_code=303)

    except ValueError as e:
        # Clean up file if ingestion fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Clean up file if ingestion fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/documents/{document_id}/reindex")
async def reindex_document_route(
    document_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reindex a document (re-run chunking and embeddings).
    """
    document = db.query(ToolkitDocument).filter(ToolkitDocument.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if file exists
    if not os.path.exists(document.file_path):
        raise HTTPException(
            status_code=400,
            detail=f"Document file not found at {document.file_path}"
        )

    try:
        # Reindex the document
        reindex_document(db=db, document_id=document_id)

        return RedirectResponse(url="/admin/documents", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reindexing failed: {str(e)}")


@router.post("/documents/{document_id}/toggle-active")
async def toggle_document_active(
    document_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Toggle document active status.
    """
    document = db.query(ToolkitDocument).filter(ToolkitDocument.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    document.is_active = not document.is_active
    db.commit()

    return RedirectResponse(url="/admin/documents", status_code=303)


# ============================================================================
# ANALYTICS
# ============================================================================

@router.get("/analytics", response_class=HTMLResponse)
async def analytics_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Analytics dashboard with platform insights.
    """
    # Top queries
    top_queries = (
        db.query(ChatLog.query, func.count(ChatLog.id).label("count"))
        .group_by(ChatLog.query)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    # Lowest rated answers
    lowest_rated = (
        db.query(ChatLog, Feedback)
        .join(Feedback, ChatLog.id == Feedback.chat_log_id)
        .filter(Feedback.rating.isnot(None))
        .order_by(Feedback.rating.asc(), Feedback.created_at.desc())
        .limit(10)
        .all()
    )

    # Issue type frequency
    issue_types = (
        db.query(Feedback.issue_type, func.count(Feedback.id).label("count"))
        .filter(Feedback.issue_type.isnot(None))
        .group_by(Feedback.issue_type)
        .order_by(desc("count"))
        .all()
    )

    # Refusal rate (answers containing refusal indicators)
    refusal_keywords = ["cannot", "unable", "don't have", "not available", "cannot provide"]
    total_answers = db.query(func.count(ChatLog.id)).scalar() or 1

    refusal_count = 0
    for keyword in refusal_keywords:
        count = db.query(func.count(ChatLog.id)).filter(
            ChatLog.answer.ilike(f"%{keyword}%")
        ).scalar()
        refusal_count += count

    # Approximate refusal rate (may count same answer multiple times)
    refusal_rate = (refusal_count / total_answers) * 100 if total_answers > 0 else 0

    # Average rating
    avg_rating = db.query(func.avg(Feedback.rating)).scalar() or 0

    # Rating distribution
    rating_dist = (
        db.query(Feedback.rating, func.count(Feedback.id).label("count"))
        .filter(Feedback.rating.isnot(None))
        .group_by(Feedback.rating)
        .order_by(Feedback.rating)
        .all()
    )

    analytics = {
        "top_queries": top_queries,
        "lowest_rated": lowest_rated,
        "issue_types": issue_types,
        "refusal_rate": round(refusal_rate, 2),
        "avg_rating": round(float(avg_rating), 2) if avg_rating else 0,
        "rating_distribution": rating_dist,
        "total_chats": total_answers,
        "total_feedback": db.query(func.count(Feedback.id)).scalar() or 0
    }

    return templates.TemplateResponse(
        "admin/analytics.html",
        {"request": request, "user": user, "analytics": analytics}
    )
