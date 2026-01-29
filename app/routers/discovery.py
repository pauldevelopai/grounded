"""Discovery routes for automated tool discovery pipeline."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin, get_current_user
from app.models.auth import User
from app.models import DiscoveredTool, DiscoveryRun, ToolMatch
from app.services.discovery.pipeline import (
    run_discovery_pipeline,
    approve_tool,
    reject_tool,
    resolve_match,
    get_tool_matches
)
from app.settings import settings
from app.templates_engine import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/discovery", tags=["discovery"])


# ============================================================================
# API KEY AUTHENTICATION FOR CRON
# ============================================================================

async def verify_api_key_or_admin(
    x_api_key: Optional[str] = Header(None),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Verify either API key (for cron) or admin session (for manual).

    Returns:
        User if authenticated via session, None if authenticated via API key

    Raises:
        HTTPException 401 if neither authentication method succeeds
    """
    # Check API key first (for cron jobs)
    api_key = getattr(settings, 'DISCOVERY_API_KEY', None)
    if x_api_key and api_key and x_api_key == api_key:
        return None  # API key auth successful, no user context

    # Check admin session
    if user and user.is_admin:
        return user

    raise HTTPException(
        status_code=401,
        detail="Invalid API key or admin access required"
    )


# ============================================================================
# API ENDPOINTS (for cron and programmatic access)
# ============================================================================

@router.post("/run")
async def trigger_discovery_run(
    sources: Optional[str] = Query(None, description="Comma-separated source types"),
    user_or_key: Optional[User] = Depends(verify_api_key_or_admin),
    db: Session = Depends(get_db)
):
    """
    Trigger a discovery run.

    Can be called by:
    - Admin users via session
    - External cron via X-API-Key header

    Query params:
        sources: Optional comma-separated source types (github, producthunt, awesome_list, directory)
    """
    # Parse sources
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",") if s.strip()]

    # Determine triggered_by
    if user_or_key:
        triggered_by = str(user_or_key.id)
    else:
        triggered_by = "cron"

    try:
        # Run discovery asynchronously
        run = await run_discovery_pipeline(
            db=db,
            sources=source_list,
            triggered_by=triggered_by
        )

        return {
            "status": "success",
            "run_id": str(run.id),
            "tools_found": run.tools_found,
            "tools_new": run.tools_new,
            "tools_updated": run.tools_updated,
            "tools_skipped": run.tools_skipped
        }

    except Exception as e:
        logger.error(f"Discovery run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run_status(
    run_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get status of a discovery run."""
    run = db.query(DiscoveryRun).filter(DiscoveryRun.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "id": str(run.id),
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "source_type": run.source_type,
        "tools_found": run.tools_found,
        "tools_new": run.tools_new,
        "tools_updated": run.tools_updated,
        "tools_skipped": run.tools_skipped,
        "error_message": run.error_message,
        "triggered_by": run.triggered_by
    }


@router.get("/api/tools")
async def list_tools_api(
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("discovered_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List discovered tools with filtering."""
    query = db.query(DiscoveredTool)

    # Apply filters
    if status:
        query = query.filter(DiscoveredTool.status == status)
    if source_type:
        query = query.filter(DiscoveredTool.source_type == source_type)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (DiscoveredTool.name.ilike(search_term)) |
            (DiscoveredTool.description.ilike(search_term)) |
            (DiscoveredTool.url.ilike(search_term))
        )

    # Count total
    total = query.count()

    # Apply sorting
    sort_column = getattr(DiscoveredTool, sort, DiscoveredTool.discovered_at)
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # Apply pagination
    tools = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "tools": [
            {
                "id": str(t.id),
                "name": t.name,
                "slug": t.slug,
                "url": t.url,
                "description": t.description[:200] + "..." if t.description and len(t.description) > 200 else t.description,
                "source_type": t.source_type,
                "source_name": t.source_name,
                "status": t.status,
                "confidence_score": t.confidence_score,
                "discovered_at": t.discovered_at.isoformat() if t.discovered_at else None,
                "categories": t.categories or []
            }
            for t in tools
        ]
    }


@router.post("/api/tools/{tool_id}/review")
async def review_tool_api(
    tool_id: str,
    status: str = Form(...),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Review a discovered tool (approve/reject)."""
    if status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    try:
        if status == "approved":
            tool = approve_tool(db, tool_id, str(user.id), notes)
        else:
            tool = reject_tool(db, tool_id, str(user.id), notes)

        return {"status": "success", "tool_status": tool.status}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/tools/bulk-review")
async def bulk_review_tools_api(
    tool_ids: str = Form(...),  # Comma-separated IDs
    status: str = Form(...),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Bulk review multiple tools."""
    if status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    ids = [id.strip() for id in tool_ids.split(",") if id.strip()]
    updated = 0

    for tool_id in ids:
        try:
            if status == "approved":
                approve_tool(db, tool_id, str(user.id), notes)
            else:
                reject_tool(db, tool_id, str(user.id), notes)
            updated += 1
        except Exception as e:
            logger.warning(f"Failed to update tool {tool_id}: {e}")

    return {"status": "success", "updated": updated}


@router.post("/api/matches/{match_id}/resolve")
async def resolve_match_api(
    match_id: str,
    is_duplicate: bool = Form(...),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Resolve a potential duplicate match."""
    try:
        match = resolve_match(db, match_id, is_duplicate, str(user.id), notes)
        return {"status": "success", "is_duplicate": match.is_duplicate}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/tools")
async def add_tool_manually(
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    source_url: str = Form(""),
    categories: str = Form(""),  # Comma-separated
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Manually add a discovered tool."""
    from app.services.discovery.dedup import extract_domain
    from app.services.discovery.pipeline import generate_slug

    # Get existing slugs
    existing_slugs = {t.slug for t in db.query(DiscoveredTool.slug).all()}

    # Parse categories
    cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else []

    tool = DiscoveredTool(
        name=name,
        slug=generate_slug(name, existing_slugs),
        url=url,
        url_domain=extract_domain(url),
        description=description,
        raw_description=description,
        categories=cat_list,
        source_type="directory",  # Manual adds are treated as directory
        source_url=source_url or url,
        source_name="Manual Entry",
        status="pending_review",
        confidence_score=1.0  # Manual adds are high confidence
    )

    db.add(tool)
    db.commit()
    db.refresh(tool)

    return {"status": "success", "tool_id": str(tool.id), "slug": tool.slug}


# ============================================================================
# ADMIN UI PAGES
# ============================================================================

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def discovery_dashboard(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Discovery dashboard with overview stats."""
    # Get stats
    total_discovered = db.query(func.count(DiscoveredTool.id)).scalar() or 0
    pending_review = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "pending_review"
    ).scalar() or 0
    approved = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "approved"
    ).scalar() or 0
    rejected = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "rejected"
    ).scalar() or 0

    # New this week
    from datetime import timedelta
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_this_week = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.discovered_at >= week_ago
    ).scalar() or 0

    # Recent runs
    recent_runs = db.query(DiscoveryRun).order_by(
        desc(DiscoveryRun.started_at)
    ).limit(10).all()

    # Source breakdown
    source_breakdown = db.query(
        DiscoveredTool.source_type,
        func.count(DiscoveredTool.id).label("count")
    ).group_by(DiscoveredTool.source_type).all()

    stats = {
        "total_discovered": total_discovered,
        "pending_review": pending_review,
        "approved": approved,
        "rejected": rejected,
        "new_this_week": new_this_week,
        "source_breakdown": dict(source_breakdown)
    }

    return templates.TemplateResponse(
        "admin/discovery/index.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_runs": recent_runs
        }
    )


@router.get("/tools", response_class=HTMLResponse)
async def discovery_tools_list(
    request: Request,
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List discovered tools with filtering."""
    per_page = 50

    # Build query
    query = db.query(DiscoveredTool)

    if status:
        query = query.filter(DiscoveredTool.status == status)
    if source_type:
        query = query.filter(DiscoveredTool.source_type == source_type)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (DiscoveredTool.name.ilike(search_term)) |
            (DiscoveredTool.description.ilike(search_term)) |
            (DiscoveredTool.url.ilike(search_term))
        )

    # Get counts for tabs
    total_all = db.query(func.count(DiscoveredTool.id)).scalar() or 0
    total_pending = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "pending_review"
    ).scalar() or 0
    total_approved = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "approved"
    ).scalar() or 0
    total_rejected = db.query(func.count(DiscoveredTool.id)).filter(
        DiscoveredTool.status == "rejected"
    ).scalar() or 0

    # Pagination
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    tools = query.order_by(
        DiscoveredTool.confidence_score.asc(),
        desc(DiscoveredTool.discovered_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    # Get match counts for each tool
    tools_with_matches = []
    for tool in tools:
        match_count = db.query(func.count(ToolMatch.id)).filter(
            ToolMatch.tool_id == tool.id,
            ToolMatch.is_duplicate.is_(None)
        ).scalar() or 0
        tools_with_matches.append({
            "tool": tool,
            "match_count": match_count
        })

    return templates.TemplateResponse(
        "admin/discovery/tools.html",
        {
            "request": request,
            "user": user,
            "tools": tools_with_matches,
            "current_status": status,
            "current_source": source_type,
            "search": search,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "counts": {
                "all": total_all,
                "pending_review": total_pending,
                "approved": total_approved,
                "rejected": total_rejected
            }
        }
    )


@router.get("/tools/{tool_id}", response_class=HTMLResponse)
async def discovery_tool_detail(
    tool_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Tool detail view with matches."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Get matches
    matches = get_tool_matches(db, tool_id)

    # Enrich matches with tool names
    enriched_matches = []
    for match in matches:
        match_info = {
            "match": match,
            "matched_tool_name": None,
            "matched_tool_url": None
        }

        if match.matched_tool_id:
            matched_tool = db.query(DiscoveredTool).filter(
                DiscoveredTool.id == match.matched_tool_id
            ).first()
            if matched_tool:
                match_info["matched_tool_name"] = matched_tool.name
                match_info["matched_tool_url"] = matched_tool.url

        if match.matched_kit_slug:
            # Try to get kit tool info
            try:
                from app.services.kit_loader import load_all_tools
                kit_tools = load_all_tools()
                kit_tool = next(
                    (t for t in kit_tools if t.get("slug") == match.matched_kit_slug),
                    None
                )
                if kit_tool:
                    match_info["matched_tool_name"] = kit_tool.get("name", match.matched_kit_slug)
                    match_info["matched_tool_url"] = kit_tool.get("url")
            except Exception:
                pass

        enriched_matches.append(match_info)

    return templates.TemplateResponse(
        "admin/discovery/tool_detail.html",
        {
            "request": request,
            "user": user,
            "tool": tool,
            "matches": enriched_matches
        }
    )


@router.post("/tools/{tool_id}/approve")
async def approve_tool_page(
    tool_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a tool (page form submission)."""
    try:
        approve_tool(db, tool_id, str(user.id), notes)
        return RedirectResponse(url=f"/admin/discovery/tools/{tool_id}", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tools/{tool_id}/reject")
async def reject_tool_page(
    tool_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject a tool (page form submission)."""
    try:
        reject_tool(db, tool_id, str(user.id), notes)
        return RedirectResponse(url=f"/admin/discovery/tools/{tool_id}", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tools/{tool_id}/edit")
async def edit_tool(
    tool_id: str,
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    categories: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Edit a discovered tool."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.name = name
    tool.url = url
    tool.description = description
    tool.categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else []
    tool.updated_at = datetime.now(timezone.utc)

    db.commit()

    return RedirectResponse(url=f"/admin/discovery/tools/{tool_id}", status_code=303)


@router.get("/matches", response_class=HTMLResponse)
async def discovery_matches_list(
    request: Request,
    resolved: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List potential duplicate matches for review."""
    per_page = 50

    query = db.query(ToolMatch)

    if resolved == "true":
        query = query.filter(ToolMatch.is_duplicate.isnot(None))
    elif resolved == "false" or resolved is None:
        query = query.filter(ToolMatch.is_duplicate.is_(None))

    # Get counts
    total_unresolved = db.query(func.count(ToolMatch.id)).filter(
        ToolMatch.is_duplicate.is_(None)
    ).scalar() or 0
    total_resolved = db.query(func.count(ToolMatch.id)).filter(
        ToolMatch.is_duplicate.isnot(None)
    ).scalar() or 0

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    matches = query.order_by(
        desc(ToolMatch.match_score),
        desc(ToolMatch.created_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    # Enrich matches
    enriched_matches = []
    for match in matches:
        tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == match.tool_id).first()
        matched_tool = None
        if match.matched_tool_id:
            matched_tool = db.query(DiscoveredTool).filter(
                DiscoveredTool.id == match.matched_tool_id
            ).first()

        enriched_matches.append({
            "match": match,
            "tool": tool,
            "matched_tool": matched_tool
        })

    return templates.TemplateResponse(
        "admin/discovery/matches.html",
        {
            "request": request,
            "user": user,
            "matches": enriched_matches,
            "resolved_filter": resolved,
            "page": page,
            "total_pages": total_pages,
            "counts": {
                "unresolved": total_unresolved,
                "resolved": total_resolved
            }
        }
    )


@router.post("/matches/{match_id}/resolve")
async def resolve_match_page(
    match_id: str,
    is_duplicate: str = Form(...),
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Resolve a match (page form submission)."""
    try:
        resolve_match(
            db,
            match_id,
            is_duplicate == "true",
            str(user.id),
            notes
        )
        return RedirectResponse(url="/admin/discovery/matches", status_code=303)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/runs", response_class=HTMLResponse)
async def discovery_runs_list(
    request: Request,
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List discovery runs."""
    per_page = 50

    query = db.query(DiscoveryRun)
    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    runs = query.order_by(
        desc(DiscoveryRun.started_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    return templates.TemplateResponse(
        "admin/discovery/runs.html",
        {
            "request": request,
            "user": user,
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
            "total": total
        }
    )
