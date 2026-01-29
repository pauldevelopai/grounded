"""Browse toolkit content routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from urllib.parse import quote, unquote

from app.db import get_db
from app.models.auth import User
from app.models.toolkit import UserActivity
from app.dependencies import get_current_user
from app.services.browse import (
    browse_chunks,
    get_available_clusters,
    get_section_detail
)
from app.templates_engine import templates


router = APIRouter(prefix="/browse", tags=["browse"])


@router.get("", response_class=HTMLResponse)
async def browse_page(
    request: Request,
    cluster: Optional[str] = None,
    keyword: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Browse toolkit content page.

    Shows all sections from toolkit_chunks with optional filters.
    No authentication required.
    """
    # Get available clusters for dropdown
    available_clusters = get_available_clusters(db)

    # Get filtered results
    results = browse_chunks(
        db=db,
        cluster=cluster,
        keyword=keyword,
        limit=100
    )

    # Log activity if user is authenticated and a search/filter was used
    if user and (keyword or cluster):
        details = {"results_count": len(results)}
        if cluster:
            details["cluster"] = cluster
        activity = UserActivity(
            user_id=user.id,
            activity_type="browse",
            query=keyword or None,
            details=details,
        )
        db.add(activity)
        db.commit()

    return templates.TemplateResponse(
        "browse/index.html",
        {
            "request": request,
            "user": user,
            "results": results,
            "available_clusters": available_clusters,
            "cluster": cluster,
            "keyword": keyword
        }
    )


@router.get("/section/{heading:path}", response_class=HTMLResponse)
async def section_detail(
    request: Request,
    heading: str,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Show detail page for a specific section.

    Displays all chunks for the section and "Ask about this" button.
    No authentication required (but login needed for ask button).
    """
    # Decode URL-encoded heading
    heading = unquote(heading)

    # Get section details
    section = get_section_detail(db, heading)

    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    return templates.TemplateResponse(
        "browse/detail.html",
        {
            "request": request,
            "user": user,
            "section": section
        }
    )
