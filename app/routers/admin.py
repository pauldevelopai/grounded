"""Admin routes for platform management."""
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin
from app.models.auth import User
from app.services.auth import hash_password
from app.models.toolkit import ToolkitDocument, ToolkitChunk, ChatLog, Feedback, UserActivity, AppFeedback
from app.models.review import ToolReview, ReviewVote, ReviewFlag
from app.services.ingestion import ingest_document, reindex_document, ingest_from_kit

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

    # App feedback stats
    app_feedback_count = db.query(func.count(AppFeedback.id)).scalar()
    app_feedback_unresolved = db.query(func.count(AppFeedback.id)).filter(AppFeedback.is_resolved == False).scalar()

    # Review stats
    review_count = db.query(func.count(ToolReview.id)).scalar()
    flagged_reviews_count = db.query(func.count(func.distinct(ReviewFlag.review_id))).filter(
        ReviewFlag.is_resolved == False
    ).scalar()

    stats = {
        "users": user_count,
        "admins": admin_count,
        "documents": document_count,
        "chunks": chunk_count,
        "chats": chat_count,
        "feedbacks": feedback_count,
        "app_feedbacks": app_feedback_count,
        "app_feedbacks_unresolved": app_feedback_unresolved,
        "reviews": review_count,
        "flagged_reviews": flagged_reviews_count
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


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: str,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    User detail page with profile info, activity summary, and management actions.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get activity summary
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Chat activity
    chat_count = db.query(func.count(ChatLog.id)).filter(ChatLog.user_id == target_user.id).scalar()
    recent_chat_count = db.query(func.count(ChatLog.id)).filter(
        ChatLog.user_id == target_user.id,
        ChatLog.created_at >= thirty_days_ago
    ).scalar()

    # User activity (tool finder, browse, etc.)
    activity_count = db.query(func.count(UserActivity.id)).filter(UserActivity.user_id == target_user.id).scalar()
    recent_activity_count = db.query(func.count(UserActivity.id)).filter(
        UserActivity.user_id == target_user.id,
        UserActivity.created_at >= thirty_days_ago
    ).scalar()

    # Feedback given
    feedback_count = db.query(func.count(Feedback.id)).filter(Feedback.user_id == target_user.id).scalar()

    # App feedback submitted
    app_feedback_count = db.query(func.count(AppFeedback.id)).filter(AppFeedback.user_id == target_user.id).scalar()

    # Recent activity timeline (last 20 items)
    recent_chats = db.query(ChatLog).filter(
        ChatLog.user_id == target_user.id
    ).order_by(ChatLog.created_at.desc()).limit(10).all()

    recent_activities = db.query(UserActivity).filter(
        UserActivity.user_id == target_user.id
    ).order_by(UserActivity.created_at.desc()).limit(10).all()

    # Combine and sort by timestamp
    timeline = []
    for chat in recent_chats:
        timeline.append({
            "type": "chat",
            "timestamp": chat.created_at,
            "query": chat.query[:100] + "..." if len(chat.query) > 100 else chat.query
        })
    for activity in recent_activities:
        timeline.append({
            "type": activity.activity_type,
            "timestamp": activity.created_at,
            "query": (activity.query[:100] + "..." if activity.query and len(activity.query) > 100 else activity.query) or "-"
        })

    timeline.sort(key=lambda x: x["timestamp"], reverse=True)
    timeline = timeline[:20]

    activity_summary = {
        "total_chats": chat_count,
        "recent_chats": recent_chat_count,
        "total_activities": activity_count,
        "recent_activities": recent_activity_count,
        "feedback_given": feedback_count,
        "app_feedback": app_feedback_count
    }

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": admin_user,
            "target_user": target_user,
            "activity_summary": activity_summary,
            "timeline": timeline
        }
    )


@router.post("/users/{user_id}/edit")
async def edit_user(
    user_id: str,
    display_name: str = Form(None),
    email: str = Form(...),
    username: str = Form(...),
    organisation: str = Form(None),
    organisation_type: str = Form(None),
    role: str = Form(None),
    country: str = Form(None),
    ai_experience_level: str = Form(None),
    # New profile fields
    interests: str = Form(None),
    bio: str = Form(None),
    website: str = Form(None),
    twitter: str = Form(None),
    linkedin: str = Form(None),
    organisation_website: str = Form(None),
    organisation_notes: str = Form(None),
    # Strategy preferences
    risk_level: str = Form(None),
    data_sensitivity: str = Form(None),
    budget: str = Form(None),
    deployment_pref: str = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Edit user profile fields.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check for email uniqueness if changed
    if email != target_user.email:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        target_user.email = email

    # Check for username uniqueness if changed
    if username != target_user.username:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already in use")
        target_user.username = username

    # Update basic fields
    target_user.display_name = display_name or None
    target_user.organisation = organisation or None
    target_user.organisation_type = organisation_type or None
    target_user.role = role or None
    target_user.country = country or None
    target_user.ai_experience_level = ai_experience_level or None
    target_user.interests = interests or None

    # Update social/bio fields
    target_user.bio = bio or None
    target_user.website = website or None
    target_user.twitter = twitter.lstrip('@') if twitter else None
    target_user.linkedin = linkedin or None
    target_user.organisation_website = organisation_website or None
    target_user.organisation_notes = organisation_notes or None

    # Update strategy preferences
    target_user.risk_level = risk_level or None
    target_user.data_sensitivity = data_sensitivity or None
    target_user.budget = budget or None
    target_user.deployment_pref = deployment_pref or None

    db.commit()

    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    new_password: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reset user password (admin action).
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate password
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    target_user.hashed_password = hash_password(new_password)
    db.commit()

    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Activate or deactivate a user account.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deactivating yourself
    if target_user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    target_user.is_active = not target_user.is_active
    db.commit()

    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a user account.
    """
    from app.models.auth import Session as SessionModel

    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting yourself
    if target_user.id == admin_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    # Delete user's sessions first
    db.query(SessionModel).filter(SessionModel.user_id == target_user.id).delete()

    # Delete user (cascades to chat_logs, feedback, user_activity, app_feedback)
    db.delete(target_user)
    db.commit()

    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/clear-history")
async def clear_user_history(
    user_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete all chat logs for a user.
    """
    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Delete all chat logs (feedback cascades)
    db.query(ChatLog).filter(ChatLog.user_id == target_user.id).delete()

    # Also delete user activities
    db.query(UserActivity).filter(UserActivity.user_id == target_user.id).delete()

    db.commit()

    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


@router.post("/users/{user_id}/insights", response_class=HTMLResponse)
async def generate_user_insights(
    user_id: str,
    request: Request,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Generate AI insights about user engagement patterns.
    """
    import os
    from openai import OpenAI

    target_user = db.query(User).filter(User.id == user_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Gather user data
    chats = db.query(ChatLog).filter(ChatLog.user_id == target_user.id).order_by(ChatLog.created_at.desc()).limit(50).all()
    activities = db.query(UserActivity).filter(UserActivity.user_id == target_user.id).order_by(UserActivity.created_at.desc()).limit(50).all()

    # Build context for AI
    chat_queries = [c.query for c in chats]
    activity_types = {}
    for a in activities:
        activity_types[a.activity_type] = activity_types.get(a.activity_type, 0) + 1

    context = f"""User Profile:
- Display Name: {target_user.display_name or 'Not set'}
- Organisation: {target_user.organisation or 'Not set'}
- Organisation Type: {target_user.organisation_type or 'Not set'}
- Role: {target_user.role or 'Not set'}
- Country: {target_user.country or 'Not set'}
- AI Experience Level: {target_user.ai_experience_level or 'Not set'}
- Account Created: {target_user.created_at.strftime('%Y-%m-%d')}

Activity Summary:
- Total chats: {len(chats)}
- Activity breakdown: {activity_types}

Recent Chat Queries (up to 50):
{chr(10).join(['- ' + q for q in chat_queries[:20]])}
"""

    # Call OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an analytics assistant helping admins understand user engagement patterns on an AI editorial toolkit learning platform. Provide concise, actionable insights."
                },
                {
                    "role": "user",
                    "content": f"""Analyze this user's engagement with the AI Editorial Toolkit platform and provide insights:

{context}

Provide:
1. A brief summary of their engagement level (2-3 sentences)
2. Their apparent interests/focus areas based on queries
3. Suggestions for content or features that might benefit them
4. Any notable patterns or concerns

Keep it concise and actionable."""
                }
            ],
            max_tokens=500
        )

        insights = response.choices[0].message.content
    except Exception as e:
        insights = f"Error generating insights: {str(e)}"

    return templates.TemplateResponse(
        "admin/user_insights.html",
        {
            "request": request,
            "user": admin_user,
            "target_user": target_user,
            "insights": insights
        }
    )


@router.post("/chats/{chat_id}/delete")
async def delete_chat_log(
    chat_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a specific chat log entry.
    """
    chat_log = db.query(ChatLog).filter(ChatLog.id == chat_id).first()

    if not chat_log:
        raise HTTPException(status_code=404, detail="Chat log not found")

    # Delete associated feedback first
    db.query(Feedback).filter(Feedback.chat_log_id == chat_id).delete()

    # Delete the chat log
    db.delete(chat_log)
    db.commit()

    return RedirectResponse(url="/admin/analytics", status_code=303)


@router.post("/chats/delete-by-query")
async def delete_chats_by_query(
    query_text: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete all chat logs matching a specific query text.
    """
    # Get all matching chat logs
    matching_chats = db.query(ChatLog).filter(ChatLog.query == query_text).all()

    # Delete associated feedback first
    for chat in matching_chats:
        db.query(Feedback).filter(Feedback.chat_log_id == chat.id).delete()

    # Delete the chat logs
    db.query(ChatLog).filter(ChatLog.query == query_text).delete()
    db.commit()

    return RedirectResponse(url="/admin/analytics", status_code=303)


# ============================================================================
# APP FEEDBACK MANAGEMENT
# ============================================================================

@router.get("/feedback", response_class=HTMLResponse)
async def list_feedback(
    request: Request,
    filter: str = "all",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all app feedback with filter options.
    """
    query = db.query(AppFeedback, User).join(User, AppFeedback.user_id == User.id)

    if filter == "unresolved":
        query = query.filter(AppFeedback.is_resolved == False)
    elif filter == "resolved":
        query = query.filter(AppFeedback.is_resolved == True)

    feedbacks = query.order_by(AppFeedback.created_at.desc()).all()

    # Get counts for tabs
    total_count = db.query(func.count(AppFeedback.id)).scalar()
    unresolved_count = db.query(func.count(AppFeedback.id)).filter(AppFeedback.is_resolved == False).scalar()
    resolved_count = db.query(func.count(AppFeedback.id)).filter(AppFeedback.is_resolved == True).scalar()

    return templates.TemplateResponse(
        "admin/feedback.html",
        {
            "request": request,
            "user": user,
            "feedbacks": feedbacks,
            "current_filter": filter,
            "counts": {
                "all": total_count,
                "unresolved": unresolved_count,
                "resolved": resolved_count
            }
        }
    )


@router.post("/feedback/{feedback_id}/resolve")
async def resolve_feedback(
    feedback_id: str,
    admin_notes: str = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Mark feedback as resolved with optional admin notes.
    """
    feedback = db.query(AppFeedback).filter(AppFeedback.id == feedback_id).first()

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback.is_resolved = True
    feedback.admin_notes = admin_notes or None
    db.commit()

    return RedirectResponse(url="/admin/feedback", status_code=303)


@router.post("/feedback/{feedback_id}/unresolve")
async def unresolve_feedback(
    feedback_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Re-open feedback (mark as unresolved).
    """
    feedback = db.query(AppFeedback).filter(AppFeedback.id == feedback_id).first()

    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    feedback.is_resolved = False
    db.commit()

    return RedirectResponse(url="/admin/feedback", status_code=303)


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
    if not (file.filename.endswith('.docx') or file.filename.endswith('.pdf')):
        raise HTTPException(status_code=400, detail="File must be a .docx or .pdf file")

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


@router.post("/documents/ingest-kit")
async def ingest_kit_route(
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Ingest toolkit content from /kit JSON files.

    Reads the structured JSON data extracted from toolkit.pdf
    and creates chunks with enriched metadata for RAG search.
    """
    try:
        from app.services.kit_loader import get_kit_stats
        stats = get_kit_stats()

        doc = ingest_from_kit(
            db=db,
            version_tag=f"kit-v1",
            create_embeddings=create_embeddings
        )

        return RedirectResponse(url="/admin/documents", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Kit ingestion failed: {str(e)}")


@router.post("/documents/ingest-batch-pdfs")
async def ingest_batch_pdfs_route(
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Ingest all batch PDF files from the /kit directory.

    Finds batch1.pdf through batch12.pdf and ingests each as a separate document.
    """
    try:
        from app.services.ingestion import ingest_batch_pdfs

        docs = ingest_batch_pdfs(
            db=db,
            create_embeddings=create_embeddings
        )

        return RedirectResponse(url="/admin/documents", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch PDF ingestion failed: {str(e)}")


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
    Analytics dashboard with app usage insights.
    """
    # Total users
    total_users = db.query(func.count(User.id)).scalar() or 0

    # Active users (users with activity in last 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    active_users = db.query(func.count(func.distinct(UserActivity.user_id))).filter(
        UserActivity.created_at >= thirty_days_ago
    ).scalar() or 0

    # Also count users with chat activity
    chat_active_users = db.query(func.count(func.distinct(ChatLog.user_id))).filter(
        ChatLog.created_at >= thirty_days_ago
    ).scalar() or 0

    # Combine active users (union of activity and chat)
    active_user_count = max(active_users, chat_active_users)

    # Total chats
    total_chats = db.query(func.count(ChatLog.id)).scalar() or 0

    # Total activities
    total_activities = db.query(func.count(UserActivity.id)).scalar() or 0

    # Activity breakdown by type
    activity_breakdown = (
        db.query(UserActivity.activity_type, func.count(UserActivity.id).label("count"))
        .group_by(UserActivity.activity_type)
        .order_by(desc("count"))
        .all()
    )

    # Top queries with user info
    top_queries_raw = (
        db.query(ChatLog.query, func.count(ChatLog.id).label("count"))
        .group_by(ChatLog.query)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    top_queries = []
    for query_text, count in top_queries_raw:
        users_who_asked = (
            db.query(User.username)
            .join(ChatLog, User.id == ChatLog.user_id)
            .filter(ChatLog.query == query_text)
            .distinct()
            .all()
        )
        usernames = [u.username for u in users_who_asked]
        top_queries.append({
            "query": query_text,
            "count": count,
            "users": usernames
        })

    # Most active users
    most_active_users = (
        db.query(
            User.username,
            func.count(ChatLog.id).label("chat_count")
        )
        .join(ChatLog, User.id == ChatLog.user_id)
        .group_by(User.id, User.username)
        .order_by(desc("chat_count"))
        .limit(10)
        .all()
    )

    # Recent activity timeline (last 20 items)
    recent_chats = (
        db.query(ChatLog, User)
        .join(User, ChatLog.user_id == User.id)
        .order_by(ChatLog.created_at.desc())
        .limit(10)
        .all()
    )

    recent_activities = (
        db.query(UserActivity, User)
        .join(User, UserActivity.user_id == User.id)
        .order_by(UserActivity.created_at.desc())
        .limit(10)
        .all()
    )

    analytics = {
        "total_users": total_users,
        "active_users": active_user_count,
        "total_chats": total_chats,
        "total_activities": total_activities,
        "activity_breakdown": activity_breakdown,
        "top_queries": top_queries,
        "most_active_users": most_active_users,
        "recent_chats": recent_chats,
        "recent_activities": recent_activities
    }

    return templates.TemplateResponse(
        "admin/analytics.html",
        {"request": request, "user": user, "analytics": analytics}
    )


# ============================================================================
# REVIEW MODERATION
# ============================================================================

@router.get("/reviews", response_class=HTMLResponse)
async def list_reviews(
    request: Request,
    filter: str = "all",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    List all reviews with filter options for moderation.
    """
    from app.schemas.review import ReviewAuthor

    # Base query
    query = db.query(ToolReview)

    if filter == "flagged":
        # Reviews with unresolved flags
        flagged_ids = db.query(ReviewFlag.review_id).filter(
            ReviewFlag.is_resolved == False
        ).distinct().subquery()
        query = query.filter(ToolReview.id.in_(flagged_ids))
    elif filter == "hidden":
        query = query.filter(ToolReview.is_hidden == True)

    reviews_raw = query.order_by(desc(ToolReview.created_at)).all()

    # Enrich reviews with additional data
    reviews = []
    for review in reviews_raw:
        # Count votes
        helpful_count = db.query(func.count(ReviewVote.id)).filter(
            ReviewVote.review_id == review.id,
            ReviewVote.is_helpful == True
        ).scalar() or 0

        not_helpful_count = db.query(func.count(ReviewVote.id)).filter(
            ReviewVote.review_id == review.id,
            ReviewVote.is_helpful == False
        ).scalar() or 0

        # Count unresolved flags
        flag_count = db.query(func.count(ReviewFlag.id)).filter(
            ReviewFlag.review_id == review.id,
            ReviewFlag.is_resolved == False
        ).scalar() or 0

        reviews.append({
            "id": review.id,
            "tool_slug": review.tool_slug,
            "rating": review.rating,
            "comment": review.comment,
            "use_case_tag": review.use_case_tag,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
            "is_hidden": review.is_hidden,
            "hidden_reason": review.hidden_reason,
            "author": ReviewAuthor(
                id=review.user.id,
                username=getattr(review.user, 'username', None),
                display_name=getattr(review.user, 'display_name', None)
            ),
            "user_email": review.user.email,
            "helpful_count": helpful_count,
            "not_helpful_count": not_helpful_count,
            "flag_count": flag_count
        })

    # Get counts for tabs
    total_count = db.query(func.count(ToolReview.id)).scalar()
    flagged_ids_subq = db.query(ReviewFlag.review_id).filter(
        ReviewFlag.is_resolved == False
    ).distinct().subquery()
    flagged_count = db.query(func.count(ToolReview.id)).filter(
        ToolReview.id.in_(flagged_ids_subq)
    ).scalar()
    hidden_count = db.query(func.count(ToolReview.id)).filter(ToolReview.is_hidden == True).scalar()

    return templates.TemplateResponse(
        "admin/reviews.html",
        {
            "request": request,
            "user": user,
            "reviews": reviews,
            "current_filter": filter,
            "counts": {
                "all": total_count,
                "flagged": flagged_count,
                "hidden": hidden_count
            }
        }
    )


@router.post("/reviews/{review_id}/hide")
async def hide_review(
    review_id: str,
    reason: str = Form(...),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Hide a review with a reason.
    """
    review = db.query(ToolReview).filter(ToolReview.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.is_hidden = True
    review.hidden_reason = reason

    # Mark all flags as resolved
    db.query(ReviewFlag).filter(ReviewFlag.review_id == review_id).update({
        "is_resolved": True,
        "resolved_by": admin_user.id,
        "resolved_at": datetime.now(timezone.utc),
        "resolution_notes": f"Review hidden: {reason}"
    })

    db.commit()

    return RedirectResponse(url="/admin/reviews", status_code=303)


@router.post("/reviews/{review_id}/restore")
async def restore_review(
    review_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Restore a hidden review.
    """
    review = db.query(ToolReview).filter(ToolReview.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.is_hidden = False
    review.hidden_reason = None
    db.commit()

    return RedirectResponse(url="/admin/reviews", status_code=303)


@router.get("/reviews/{review_id}/flags")
async def get_review_flags(
    review_id: str,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Get all flags for a review.
    """
    flags = db.query(ReviewFlag).filter(
        ReviewFlag.review_id == review_id
    ).order_by(desc(ReviewFlag.created_at)).all()

    return [
        {
            "id": str(flag.id),
            "reason": flag.reason,
            "details": flag.details,
            "created_at": flag.created_at.isoformat(),
            "user_id": str(flag.user_id),
            "is_resolved": flag.is_resolved
        }
        for flag in flags
    ]
