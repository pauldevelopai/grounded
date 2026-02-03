"""Admin routes for platform management."""
import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Request, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin
from app.models.auth import User
from app.services.auth import hash_password
from app.models.toolkit import ToolkitDocument, ToolkitChunk, ChatLog, Feedback, UserActivity, AppFeedback, StrategyPlan
from app.models.review import ToolReview, ReviewVote, ReviewFlag
from app.models.discovery import DiscoveredTool
from app.models.suggested_source import SuggestedSource
from app.services.ingestion import (
    ingest_document, reindex_document, ingest_from_kit,
    save_document_only, ingest_existing_document, uningest_document
)
from app.templates_engine import templates
from app.products.admin_context import (
    get_admin_context_dict,
    set_admin_context_cookies,
    validate_admin_context,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Data directory for uploads (persistent filesystem)
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")


# =============================================================================
# MASTER ADMIN & CONTEXT SWITCHING
# =============================================================================

@router.get("/master", response_class=HTMLResponse)
async def master_dashboard(
    request: Request,
    user: User = Depends(require_admin),
):
    """
    Master admin dashboard showing all products and editions.
    This is the global overview for managing all apps.
    """
    # Get admin context (includes all products and current selection)
    context = get_admin_context_dict(request)

    return templates.TemplateResponse(
        "admin/master.html",
        {
            "request": request,
            "user": user,
            **context,
            "active_admin_page": "master",
        }
    )


@router.get("/context/switch", response_class=HTMLResponse)
async def switch_context(
    request: Request,
    product: str = Query(..., description="Product ID to switch to"),
    edition: Optional[str] = Query(None, description="Edition version to switch to"),
    user: User = Depends(require_admin),
):
    """
    Switch the admin context to a different product/edition.
    Sets cookies and redirects back to the referring page or master dashboard.
    """
    # Validate the context
    is_valid, error = validate_admin_context(product, edition)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    # Get redirect URL (referer or master dashboard)
    referer = request.headers.get("referer", "/admin/master")
    # Don't redirect back to the switch endpoint
    if "/context/switch" in referer:
        referer = "/admin/master"

    # Create response with redirect
    response = RedirectResponse(url=referer, status_code=303)

    # Set context cookies
    set_admin_context_cookies(response, product, edition)

    return response


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin dashboard homepage with overview stats.
    Stats are shown for the current admin context (product/edition).

    Note: If no edition cookie is set OR if the cookie is set to a non-active edition,
    we explicitly set it to the active edition to prevent accidentally landing on an old edition.
    """
    from app.products.admin_context import ADMIN_EDITION_KEY
    from app.products.registry import EditionRegistry

    current_cookie = request.cookies.get(ADMIN_EDITION_KEY)
    active_edition = EditionRegistry.get_active("grounded")
    active_version = active_edition.version if active_edition else "v2"

    # Set cookie if: no cookie, or cookie is set to non-active edition
    needs_edition_cookie = (not current_cookie) or (current_cookie != active_version)

    # Get admin context
    admin_context = get_admin_context_dict(request)

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

    # Discovery stats
    discovered_tools_count = db.query(func.count(DiscoveredTool.id)).scalar() or 0
    pending_discovery_count = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "pending_review"
    ).scalar() or 0

    # Suggested sources stats
    pending_sources_count = db.query(func.count(SuggestedSource.id)).filter(
        SuggestedSource.status == "pending"
    ).scalar() or 0

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
        "flagged_reviews": flagged_reviews_count,
        "discovered_tools": discovered_tools_count,
        "pending_discovery": pending_discovery_count,
        "pending_sources": pending_sources_count
    }

    response = templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            **admin_context,
            "active_admin_page": "dashboard",
        }
    )

    # Set edition cookie to active edition if not already set
    if needs_edition_cookie and admin_context.get("admin_edition_version"):
        set_admin_context_cookies(
            response,
            admin_context.get("admin_product_id", "grounded"),
            admin_context.get("admin_edition_version")
        )

    return response


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
    admin_context = get_admin_context_dict(request)
    users = db.query(User).order_by(User.created_at.desc()).all()

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "user": user,
            "users": users,
            **admin_context,
            "active_admin_page": "users",
        }
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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": admin_user,
            "target_user": target_user,
            "activity_summary": activity_summary,
            "timeline": timeline,
            **admin_context,
            "active_admin_page": "users",
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
                    "content": f"""Analyze this user's engagement with the Grounded platform and provide insights:

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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/user_insights.html",
        {
            "request": request,
            "user": admin_user,
            "target_user": target_user,
            "insights": insights,
            **admin_context,
            "active_admin_page": "users",
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

    admin_context = get_admin_context_dict(request)
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
            },
            **admin_context,
            "active_admin_page": "feedback",
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
            "is_active": doc.is_active,
            "is_ingested": doc.is_ingested
        })

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/documents.html",
        {
            "request": request,
            "user": user,
            "documents": docs_with_counts,
            **admin_context,
            "active_admin_page": "documents",
        }
    )


@router.get("/documents/upload", response_class=HTMLResponse)
async def upload_document_page(
    request: Request,
    user: User = Depends(require_admin)
):
    """
    Document upload page.
    """
    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/upload.html",
        {
            "request": request,
            "user": user,
            **admin_context,
            "active_admin_page": "documents",
        }
    )


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    version_tag: str = Form(...),
    ingest_now: bool = Form(False),
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Upload a new document, optionally ingesting immediately.
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
        if ingest_now:
            # Ingest document immediately
            doc = ingest_document(
                db=db,
                file_path=file_path,
                version_tag=version_tag,
                source_filename=file.filename,
                create_embeddings=create_embeddings
            )
        else:
            # Just save document record without ingesting
            doc = save_document_only(
                db=db,
                file_path=file_path,
                version_tag=version_tag,
                source_filename=file.filename
            )

        return RedirectResponse(url="/admin/documents", status_code=303)

    except ValueError as e:
        # Clean up file if save fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Clean up file if save fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


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


@router.post("/documents/{document_id}/delete")
async def delete_document(
    document_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a document and all its chunks.
    """
    document = db.query(ToolkitDocument).filter(ToolkitDocument.id == document_id).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete all chunks first
    db.query(ToolkitChunk).filter(ToolkitChunk.document_id == document_id).delete()

    # Delete the document
    db.delete(document)
    db.commit()

    return RedirectResponse(url="/admin/documents", status_code=303)


@router.post("/documents/{document_id}/ingest")
async def ingest_document_route(
    document_id: str,
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Ingest a pending document (create chunks and embeddings).
    """
    try:
        doc = ingest_existing_document(
            db=db,
            document_id=document_id,
            create_embeddings=create_embeddings
        )
        return RedirectResponse(url="/admin/documents", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/documents/{document_id}/uningest")
async def uningest_document_route(
    document_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Remove ingestion from a document (delete chunks but keep document).
    """
    try:
        doc = uningest_document(db=db, document_id=document_id)
        return RedirectResponse(url="/admin/documents", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Un-ingestion failed: {str(e)}")


@router.post("/documents/ingest-approved-tools")
async def ingest_approved_tools_route(
    create_embeddings: bool = Form(True),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Ingest all approved tools from the discovery system.

    Creates searchable content for each approved tool with their
    descriptions, categories, and metadata.
    """
    try:
        from app.services.ingestion import ingest_approved_tools

        doc = ingest_approved_tools(
            db=db,
            create_embeddings=create_embeddings
        )

        return RedirectResponse(url="/admin/documents", status_code=303)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approved tools ingestion failed: {str(e)}")


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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/analytics.html",
        {
            "request": request,
            "user": user,
            "analytics": analytics,
            **admin_context,
            "active_admin_page": "analytics",
        }
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

    admin_context = get_admin_context_dict(request)
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
            },
            **admin_context,
            "active_admin_page": "reviews",
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


# =============================================================================
# SUGGESTED SOURCES MANAGEMENT
# =============================================================================

@router.get("/sources", response_class=HTMLResponse)
async def admin_suggested_sources(
    request: Request,
    status: Optional[str] = Query(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all suggested sources for admin review."""
    query = db.query(SuggestedSource)

    if status and status in ('pending', 'approved', 'rejected'):
        query = query.filter(SuggestedSource.status == status)

    suggestions = query.order_by(desc(SuggestedSource.created_at)).all()

    # Get counts by status
    pending_count = db.query(SuggestedSource).filter(SuggestedSource.status == 'pending').count()
    approved_count = db.query(SuggestedSource).filter(SuggestedSource.status == 'approved').count()
    rejected_count = db.query(SuggestedSource).filter(SuggestedSource.status == 'rejected').count()

    return templates.TemplateResponse(
        "admin/suggested_sources.html",
        {
            "request": request,
            "user": admin_user,
            "suggestions": suggestions,
            "status_filter": status or "",
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "active_admin_page": "sources",
        }
    )


@router.post("/sources/{suggestion_id}/approve")
async def approve_suggested_source(
    suggestion_id: str,
    review_notes: Optional[str] = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a suggested source."""
    suggestion = db.query(SuggestedSource).filter(SuggestedSource.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.status = "approved"
    suggestion.reviewed_by = admin_user.id
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.review_notes = review_notes or "Approved and added to sources library."

    db.commit()

    return RedirectResponse(url="/admin/sources?status=pending", status_code=303)


@router.post("/sources/{suggestion_id}/reject")
async def reject_suggested_source(
    suggestion_id: str,
    review_notes: Optional[str] = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject a suggested source."""
    suggestion = db.query(SuggestedSource).filter(SuggestedSource.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.status = "rejected"
    suggestion.reviewed_by = admin_user.id
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.review_notes = review_notes or "Does not meet our criteria for inclusion."

    db.commit()

    return RedirectResponse(url="/admin/sources?status=pending", status_code=303)


# =============================================================================
# TRAINING DATA MANAGEMENT
# =============================================================================

@router.get("/training", response_class=HTMLResponse)
async def admin_training(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Training data management page."""
    from app.services.kit_loader import get_all_tools, get_all_clusters, get_all_sources

    # Get chunk stats by type (metadata uses 'type' key)
    chunk_type_stats = db.query(
        ToolkitChunk.chunk_metadata['type'].astext.label('type'),
        func.count(ToolkitChunk.id).label('count')
    ).group_by('type').all()

    chunk_types = [{"type": ct.type or "unknown", "count": ct.count} for ct in chunk_type_stats]

    # Calculate totals
    total_chunks = sum(ct["count"] for ct in chunk_types)
    tool_chunks = sum(ct["count"] for ct in chunk_types if ct["type"] == "tool")
    source_chunks = sum(ct["count"] for ct in chunk_types if ct["type"] in ("source", "source_pdf"))
    other_chunks = total_chunks - tool_chunks - source_chunks

    # Get kit stats
    kit_tools = len(get_all_tools())
    kit_clusters = len(get_all_clusters()) + 1  # +1 for admin-approved cluster

    # Get source stats
    sources_data = get_all_sources()
    static_sources = sources_data.get("total_entries", 0)
    community_sources = db.query(SuggestedSource).filter(SuggestedSource.status == "approved").count()

    # Calculate indexed source chunks
    indexed_source_chunks = sum(ct["count"] for ct in chunk_types if ct["type"] in ("source", "source_pdf"))

    # Get user activity stats
    user_activities = db.query(UserActivity).count()
    active_users = db.query(func.count(func.distinct(UserActivity.user_id))).scalar() or 0

    # ============================================
    # USER ACTIVITY DATA FOR RECOMMENDATIONS
    # ============================================

    # Activity breakdown by type
    activity_breakdown = (
        db.query(UserActivity.activity_type, func.count(UserActivity.id).label("count"))
        .group_by(UserActivity.activity_type)
        .order_by(desc("count"))
        .all()
    )

    # Get users with most activity (top 10)
    users_with_activity = (
        db.query(
            User.id,
            User.email,
            User.display_name,
            User.ai_experience_level,
            User.budget,
            User.data_sensitivity,
            func.count(UserActivity.id).label("activity_count")
        )
        .join(UserActivity, User.id == UserActivity.user_id)
        .group_by(User.id)
        .order_by(desc("activity_count"))
        .limit(10)
        .all()
    )

    # For each top user, get their activity signals that feed recommendations
    user_activity_details = []
    for u in users_with_activity:
        # Get recent activities for this user
        user_activities_list = db.query(UserActivity).filter(
            UserActivity.user_id == u.id
        ).order_by(desc(UserActivity.created_at)).limit(50).all()

        # Extract activity signals (same logic as recommendation service)
        searched_queries = []
        browsed_clusters = []
        viewed_tools = []

        for activity in user_activities_list:
            if activity.activity_type == "tool_search" and activity.query:
                if activity.query not in searched_queries:
                    searched_queries.append(activity.query)
            elif activity.activity_type == "tool_finder" and activity.details:
                need = activity.details.get("need")
                if need and need not in browsed_clusters:
                    browsed_clusters.append(need)
            elif activity.activity_type == "tool_view" and activity.details:
                tool_slug = activity.details.get("tool_slug")
                if tool_slug and tool_slug not in viewed_tools:
                    viewed_tools.append(tool_slug)
            elif activity.activity_type == "browse" and activity.details:
                cluster = activity.details.get("cluster")
                if cluster and cluster not in browsed_clusters:
                    browsed_clusters.append(cluster)

        # Count recommendation_shown activities
        rec_shown_count = sum(1 for a in user_activities_list if a.activity_type == "recommendation_shown")

        user_activity_details.append({
            "user_id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "ai_experience_level": u.ai_experience_level,
            "budget": u.budget,
            "data_sensitivity": u.data_sensitivity,
            "activity_count": u.activity_count,
            "searched_queries": searched_queries[:5],
            "browsed_clusters": browsed_clusters[:5],
            "viewed_tools": viewed_tools[:5],
            "recommendations_served": rec_shown_count,
        })

    # Recent activity log (last 20)
    recent_activities = (
        db.query(UserActivity, User)
        .join(User, UserActivity.user_id == User.id)
        .order_by(desc(UserActivity.created_at))
        .limit(20)
        .all()
    )

    # ============================================
    # STRATEGY GENERATION DATA
    # ============================================

    # Total strategies generated
    total_strategies = db.query(func.count(StrategyPlan.id)).scalar() or 0

    # Strategies by user (top 10)
    strategies_by_user = (
        db.query(
            User.id,
            User.email,
            User.display_name,
            func.count(StrategyPlan.id).label("strategy_count")
        )
        .join(StrategyPlan, User.id == StrategyPlan.user_id)
        .group_by(User.id)
        .order_by(desc("strategy_count"))
        .limit(10)
        .all()
    )

    # Recent strategies with input data analysis
    recent_strategies = (
        db.query(StrategyPlan, User)
        .join(User, StrategyPlan.user_id == User.id)
        .order_by(desc(StrategyPlan.created_at))
        .limit(10)
        .all()
    )

    # Analyze strategy inputs
    strategy_details = []
    for strategy, strategy_user in recent_strategies:
        inputs = strategy.inputs or {}

        # Check which profile fields were populated
        populated_fields = []
        if inputs.get('role'):
            populated_fields.append('role')
        if inputs.get('org_type'):
            populated_fields.append('org_type')
        if inputs.get('risk_level'):
            populated_fields.append('risk_level')
        if inputs.get('data_sensitivity'):
            populated_fields.append('data_sensitivity')
        if inputs.get('budget'):
            populated_fields.append('budget')
        if inputs.get('deployment_pref'):
            populated_fields.append('deployment_pref')
        if inputs.get('use_cases'):
            populated_fields.append('use_cases')

        # Check if activity was included
        has_activity = 'activity_summary' in inputs
        activity_data = inputs.get('activity_summary', {})

        strategy_details.append({
            "id": str(strategy.id),
            "user_email": strategy_user.email,
            "user_display_name": strategy_user.display_name,
            "created_at": strategy.created_at,
            "inputs": inputs,
            "populated_fields": populated_fields,
            "populated_count": len(populated_fields),
            "has_activity": has_activity,
            "activity_searches": activity_data.get('tool_searches', [])[:3] if has_activity else [],
            "citations_count": len(strategy.citations) if strategy.citations else 0,
        })

    # Count strategies with activity data
    strategies_with_activity = sum(1 for s in strategy_details if s['has_activity'])

    # Count strategies with complete profile
    strategies_with_full_profile = sum(1 for s in strategy_details if s['populated_count'] >= 5)

    stats = {
        "total_chunks": total_chunks,
        "tool_chunks": tool_chunks,
        "source_chunks": source_chunks,
        "other_chunks": other_chunks,
        "kit_tools": kit_tools,
        "kit_clusters": kit_clusters,
        "static_sources": static_sources,
        "community_sources": community_sources,
        "indexed_source_chunks": indexed_source_chunks,
        "user_activities": user_activities,
        "active_users": active_users,
    }

    return templates.TemplateResponse(
        "admin/training.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "chunk_types": chunk_types,
            "activity_breakdown": activity_breakdown,
            "user_activity_details": user_activity_details,
            "recent_activities": recent_activities,
            # Strategy generation data
            "total_strategies": total_strategies,
            "strategies_by_user": strategies_by_user,
            "strategy_details": strategy_details,
            "strategies_with_activity": strategies_with_activity,
            "strategies_with_full_profile": strategies_with_full_profile,
            "active_admin_page": "training",
        }
    )


@router.post("/training/ingest-sources")
async def ingest_sources(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Ingest all sources into the RAG system."""
    # This would trigger source ingestion
    # For now, redirect with a message
    return RedirectResponse(url="/admin/training", status_code=303)


@router.post("/training/clear-embeddings")
async def clear_embeddings(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Clear all embeddings from the system."""
    # Delete all chunks
    db.query(ToolkitChunk).delete()
    db.commit()

    return RedirectResponse(url="/admin/training", status_code=303)


# =============================================================================
# TOOL SUGGESTIONS MANAGEMENT
# =============================================================================

@router.get("/tool-suggestions", response_class=HTMLResponse)
async def admin_tool_suggestions(
    request: Request,
    status: Optional[str] = Query(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all tool suggestions for admin review."""
    from app.models.tool_suggestion import ToolSuggestion

    query = db.query(ToolSuggestion)

    if status and status in ('pending', 'approved', 'rejected', 'converted'):
        query = query.filter(ToolSuggestion.status == status)

    suggestions = query.order_by(desc(ToolSuggestion.submitted_at)).all()

    # Get counts by status
    pending_count = db.query(ToolSuggestion).filter(ToolSuggestion.status == 'pending').count()
    approved_count = db.query(ToolSuggestion).filter(ToolSuggestion.status == 'approved').count()
    rejected_count = db.query(ToolSuggestion).filter(ToolSuggestion.status == 'rejected').count()
    converted_count = db.query(ToolSuggestion).filter(ToolSuggestion.status == 'converted').count()
    total_count = pending_count + approved_count + rejected_count + converted_count

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/tool_suggestions.html",
        {
            "request": request,
            "user": admin_user,
            "suggestions": suggestions,
            "status_filter": status or "",
            "pending_count": pending_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "converted_count": converted_count,
            "total_count": total_count,
            **admin_context,
            "active_admin_page": "tool_suggestions",
        }
    )


@router.post("/tool-suggestions/{suggestion_id}/approve")
async def approve_tool_suggestion(
    suggestion_id: str,
    review_notes: Optional[str] = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a tool suggestion and convert it to a DiscoveredTool."""
    from app.models.tool_suggestion import ToolSuggestion
    from app.services.discovery.dedup import extract_domain
    from app.services.discovery.pipeline import generate_slug

    suggestion = db.query(ToolSuggestion).filter(ToolSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Get existing slugs for uniqueness check
    existing_slugs = {t.slug for t in db.query(DiscoveredTool.slug).all()}

    # Create DiscoveredTool from suggestion
    tool = DiscoveredTool(
        name=suggestion.name,
        slug=generate_slug(suggestion.name, existing_slugs),
        url=suggestion.url,
        url_domain=extract_domain(suggestion.url),
        description=suggestion.description,
        raw_description=suggestion.description,
        purpose=suggestion.use_cases,
        source_type="directory",  # User suggestions treated as directory
        source_url=suggestion.url,
        source_name="User Suggestion",
        status="approved",  # Pre-approved since admin is approving the suggestion
        confidence_score=1.0,  # High confidence - admin approved
        reviewed_by=admin_user.id,
        reviewed_at=datetime.now(timezone.utc),
        review_notes=review_notes or f"Converted from user suggestion by {suggestion.submitter.email}",
    )

    db.add(tool)
    db.flush()  # Get the tool ID

    # Update suggestion status
    suggestion.status = "converted"
    suggestion.reviewed_by = admin_user.id
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.review_notes = review_notes or "Approved and converted to tool."
    suggestion.converted_tool_id = tool.id

    db.commit()

    return RedirectResponse(url="/admin/tool-suggestions?status=pending", status_code=303)


@router.post("/tool-suggestions/{suggestion_id}/reject")
async def reject_tool_suggestion(
    suggestion_id: str,
    review_notes: Optional[str] = Form(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject a tool suggestion."""
    from app.models.tool_suggestion import ToolSuggestion

    suggestion = db.query(ToolSuggestion).filter(ToolSuggestion.id == suggestion_id).first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    suggestion.status = "rejected"
    suggestion.reviewed_by = admin_user.id
    suggestion.reviewed_at = datetime.now(timezone.utc)
    suggestion.review_notes = review_notes or "Does not meet our criteria for inclusion."

    db.commit()

    return RedirectResponse(url="/admin/tool-suggestions?status=pending", status_code=303)
