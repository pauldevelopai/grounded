"""Source citation routes (grounded link extracts from batch PDFs)."""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Request, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.suggested_source import SuggestedSource
from app.dependencies import get_current_user
from app.services.kit_loader import (
    get_all_sources, get_source_batch, search_sources
)
from app.templates_engine import templates


router = APIRouter(prefix="/sources", tags=["sources"])

# Batch 13 is reserved for community-submitted sources
COMMUNITY_BATCH_NUM = 13
COMMUNITY_BATCH_THEME = "Community Submitted"


def infer_source_type(url: str) -> str:
    """Infer source type from URL."""
    url_lower = (url or "").lower()
    if any(x in url_lower for x in ['.pdf', 'oecd.org', 'linuxfoundation.org', 'unesco.org', 'artificialintelligenceact.eu']):
        return 'report'
    elif any(x in url_lower for x in ['researchgate.net', 'arxiv.org', 'doi.org', 'academic', 'journal', 'springer', 'wiley']):
        return 'study'
    return 'article'


def get_approved_sources(db: Session) -> List[Dict[str, Any]]:
    """Get all approved user-submitted sources formatted as source entries."""
    approved = db.query(SuggestedSource).filter(
        SuggestedSource.status == "approved"
    ).order_by(SuggestedSource.reviewed_at.desc()).all()

    entries = []
    for i, src in enumerate(approved, 1):
        entries.append({
            "batch": COMMUNITY_BATCH_NUM,
            "entry_id": f"community-{src.id}",
            "title": src.title,
            "url": src.url,
            "source": "",
            "date": src.reviewed_at.strftime("%Y-%m-%d") if src.reviewed_at else "",
            "excerpt": src.excerpt or "",
            "why_it_matters": src.why_valuable or "",
            "ai_extract": "",
            "theme": COMMUNITY_BATCH_THEME,
        })
    return entries


def get_all_sources_with_community(db: Session) -> Dict[str, Any]:
    """Get all sources including community-submitted ones."""
    base_data = get_all_sources()
    approved_entries = get_approved_sources(db)

    # Build combined data
    batches = list(base_data.get("batches", []))
    entries = list(base_data.get("entries", []))

    # Add community batch if there are approved sources
    if approved_entries:
        batches.append({
            "batch": COMMUNITY_BATCH_NUM,
            "theme": COMMUNITY_BATCH_THEME,
            "entry_count": len(approved_entries),
        })
        entries.extend(approved_entries)

    return {
        "total_entries": len(entries),
        "batch_count": len(batches),
        "batches": batches,
        "entries": entries,
    }


@router.get("", response_class=HTMLResponse)
async def sources_index(
    request: Request,
    batch: Optional[str] = Query(None),
    q: Optional[str] = None,
    source_type: Optional[str] = Query(None),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all grounded citation sources with optional batch/search/type filter."""
    # Convert batch to int if provided (handle empty string)
    batch_num = None
    if batch and batch.strip():
        try:
            batch_num = int(batch)
            if batch_num < 1 or batch_num > COMMUNITY_BATCH_NUM:
                batch_num = None
        except ValueError:
            batch_num = None

    # Get all data including community sources
    all_data = get_all_sources_with_community(db)

    if q:
        # Search in both static and community sources
        static_results = search_sources(q)
        community_entries = get_approved_sources(db)
        q_lower = q.lower()
        community_results = [
            e for e in community_entries
            if q_lower in e.get("title", "").lower() or q_lower in e.get("excerpt", "").lower()
        ]
        entries = static_results + community_results
    elif batch_num == COMMUNITY_BATCH_NUM:
        # Show only community sources
        entries = get_approved_sources(db)
    elif batch_num:
        batch_data = get_source_batch(batch_num)
        entries = batch_data["entries"] if batch_data else []
    else:
        entries = []  # Default: show batches only, no entries

    # Filter by source type if specified
    if source_type and source_type in ('article', 'report', 'study'):
        entries = [e for e in entries if infer_source_type(e.get("url", "")) == source_type]

    return templates.TemplateResponse(
        "sources/index.html",
        {
            "request": request,
            "user": user,
            "entries": entries,
            "batches": all_data.get("batches", []),
            "total_entries": all_data.get("total_entries", 0),
            "selected_batch": batch_num,
            "source_type": source_type or "",
            "q": q or "",
        }
    )


@router.get("/batch/{batch_num}", response_class=HTMLResponse)
async def source_batch_detail(
    request: Request,
    batch_num: int,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Show all entries from a specific batch."""
    all_data = get_all_sources_with_community(db)

    if batch_num == COMMUNITY_BATCH_NUM:
        # Community batch
        entries = get_approved_sources(db)
        batch_data = {
            "batch": COMMUNITY_BATCH_NUM,
            "theme": COMMUNITY_BATCH_THEME,
            "entries": entries,
        } if entries else None
    else:
        batch_data = get_source_batch(batch_num)

    return templates.TemplateResponse(
        "sources/batch.html",
        {
            "request": request,
            "user": user,
            "batch": batch_data,
            "batch_num": batch_num,
            "batches": all_data.get("batches", []),
        }
    )


@router.get("/suggest", response_class=HTMLResponse)
async def suggest_source_form(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Form to suggest a new source."""
    # Get user's previous suggestions
    my_suggestions = []
    if user:
        my_suggestions = db.query(SuggestedSource).filter(
            SuggestedSource.submitted_by == user.id
        ).order_by(SuggestedSource.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "sources/suggest.html",
        {
            "request": request,
            "user": user,
            "my_suggestions": my_suggestions,
        }
    )


@router.post("/suggest", response_class=HTMLResponse)
async def submit_source_suggestion(
    request: Request,
    title: str = Form(...),
    url: str = Form(...),
    source_type: str = Form("article"),
    excerpt: Optional[str] = Form(None),
    why_valuable: Optional[str] = Form(None),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a source suggestion."""
    if not user:
        return templates.TemplateResponse(
            "sources/suggest.html",
            {
                "request": request,
                "user": None,
                "error": "You must be logged in to suggest a source.",
                "my_suggestions": [],
            }
        )

    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Check for duplicate URL from this user
    existing = db.query(SuggestedSource).filter(
        SuggestedSource.url == url,
        SuggestedSource.submitted_by == user.id
    ).first()

    if existing:
        my_suggestions = db.query(SuggestedSource).filter(
            SuggestedSource.submitted_by == user.id
        ).order_by(SuggestedSource.created_at.desc()).limit(10).all()

        return templates.TemplateResponse(
            "sources/suggest.html",
            {
                "request": request,
                "user": user,
                "error": "You have already suggested this source.",
                "my_suggestions": my_suggestions,
            }
        )

    # Create suggestion
    suggestion = SuggestedSource(
        submitted_by=user.id,
        title=title.strip(),
        url=url.strip(),
        source_type=source_type,
        excerpt=excerpt.strip() if excerpt else None,
        why_valuable=why_valuable.strip() if why_valuable else None,
    )

    db.add(suggestion)
    db.commit()

    # Get updated suggestions list
    my_suggestions = db.query(SuggestedSource).filter(
        SuggestedSource.submitted_by == user.id
    ).order_by(SuggestedSource.created_at.desc()).limit(10).all()

    return templates.TemplateResponse(
        "sources/suggest.html",
        {
            "request": request,
            "user": user,
            "success": "Thank you! Your source suggestion has been submitted for review.",
            "my_suggestions": my_suggestions,
        }
    )
