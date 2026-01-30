"""Discovery routes for automated tool discovery pipeline."""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Header, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin, get_current_user
from app.models.auth import User
from app.models import DiscoveredTool, DiscoveryRun, ToolMatch, DiscoveredResource, UseCase
from app.services.discovery.pipeline import (
    run_discovery_pipeline,
    approve_tool,
    reject_tool,
    resolve_match,
    get_tool_matches
)
from app.settings import settings
from app.templates_engine import templates
from app.products.guards import require_feature
from app.products.admin_context import get_admin_context_dict

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/discovery",
    tags=["discovery"],
    dependencies=[Depends(require_feature("admin_discovery"))]  # Requires admin discovery feature
)


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


@router.post("/run-resources")
async def trigger_resource_discovery(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Trigger resource discovery run.
    TODO: Implement actual resource discovery pipeline.
    """
    # Placeholder - redirect back with message
    return RedirectResponse(
        url="/admin/discovery/resources",
        status_code=303
    )


@router.post("/run-usecases")
async def trigger_usecase_discovery(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Trigger use case discovery run.
    TODO: Implement actual use case discovery pipeline.
    """
    # Placeholder - redirect back with message
    return RedirectResponse(
        url="/admin/discovery/use-cases",
        status_code=303
    )


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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/index.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_runs": recent_runs,
            **admin_context,
            "active_admin_page": "discovery",
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

    admin_context = get_admin_context_dict(request)
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
            },
            **admin_context,
            "active_admin_page": "discovery",
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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/tool_detail.html",
        {
            "request": request,
            "user": user,
            "tool": tool,
            "matches": enriched_matches,
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


@router.post("/tools/{tool_id}/approve")
async def approve_tool_page(
    tool_id: str,
    notes: Optional[str] = Form(None),
    cdi_cost: Optional[int] = Form(None),
    cdi_difficulty: Optional[int] = Form(None),
    cdi_invasiveness: Optional[int] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a tool with optional CDI scores (page form submission)."""
    try:
        approve_tool(
            db, tool_id, str(user.id), notes,
            cdi_cost=cdi_cost,
            cdi_difficulty=cdi_difficulty,
            cdi_invasiveness=cdi_invasiveness
        )
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
    purpose: str = Form(""),
    ai_summary: str = Form(""),
    categories: str = Form(""),
    github_url: str = Form(""),
    docs_url: str = Form(""),
    pricing_url: str = Form(""),
    cdi_cost: Optional[int] = Form(None),
    cdi_difficulty: Optional[int] = Form(None),
    cdi_invasiveness: Optional[int] = Form(None),
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
    tool.purpose = purpose if purpose else None
    tool.ai_summary = ai_summary if ai_summary else None
    tool.categories = [c.strip() for c in categories.split(",") if c.strip()] if categories else []
    tool.github_url = github_url if github_url else None
    tool.docs_url = docs_url if docs_url else None
    tool.pricing_url = pricing_url if pricing_url else None

    # CDI scores (validate 0-10 range)
    if cdi_cost is not None:
        tool.cdi_cost = max(0, min(10, cdi_cost))
    if cdi_difficulty is not None:
        tool.cdi_difficulty = max(0, min(10, cdi_difficulty))
    if cdi_invasiveness is not None:
        tool.cdi_invasiveness = max(0, min(10, cdi_invasiveness))

    tool.updated_at = datetime.now(timezone.utc)

    db.commit()

    return RedirectResponse(url=f"/admin/discovery/tools/{tool_id}", status_code=303)


@router.post("/tools/{tool_id}/enrich")
async def enrich_tool_page(
    tool_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Re-enrich a tool by fetching fresh content from its website and generating AI descriptions."""
    from app.services.discovery.enrichment import enrich_tool_by_id

    tool = enrich_tool_by_id(db, tool_id)

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

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

    admin_context = get_admin_context_dict(request)
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
            },
            **admin_context,
            "active_admin_page": "discovery",
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

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/runs.html",
        {
            "request": request,
            "user": user,
            "runs": runs,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


# Approved tools page - separate router to be at /admin/approved-tools
approved_router = APIRouter(
    prefix="/admin/approved-tools",
    tags=["approved-tools"],
)


@approved_router.get("", response_class=HTMLResponse)
@approved_router.get("/", response_class=HTMLResponse)
async def approved_tools_list(
    request: Request,
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List approved tools ready for addition to the kit."""
    per_page = 50

    query = db.query(DiscoveredTool).filter(DiscoveredTool.status == "approved")

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (DiscoveredTool.name.ilike(search_term)) |
            (DiscoveredTool.description.ilike(search_term))
        )

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    tools = query.order_by(
        desc(DiscoveredTool.reviewed_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/approved_tools.html",
        {
            "request": request,
            "user": user,
            "tools": tools,
            "search": search,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            **admin_context,
            "active_admin_page": "approved_tools",
        }
    )


@approved_router.post("/{tool_id}/add-to-kit")
async def add_to_kit(
    tool_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Mark a tool as added to the kit."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.status = "in_kit"
    tool.updated_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url="/admin/approved-tools", status_code=303)


@approved_router.post("/{tool_id}/remove")
async def remove_approved_tool(
    tool_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Remove approval from a tool (send back to pending review)."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.status = "pending_review"
    tool.reviewed_at = None
    tool.reviewed_by = None
    tool.review_notes = f"Approval removed by admin on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    tool.updated_at = datetime.now(timezone.utc)
    db.commit()

    return RedirectResponse(url="/admin/approved-tools", status_code=303)


# ============================================================================
# RESOURCES ROUTES
# ============================================================================

def generate_resource_slug(title: str, existing_slugs: set[str] | None = None) -> str:
    """Generate a URL-friendly slug from resource title."""
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    slug = slug[:80]  # Limit length

    if existing_slugs:
        base_slug = slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

    return slug


@router.get("/resources", response_class=HTMLResponse)
async def discovery_resources_list(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List discovered resources."""
    per_page = 50

    query = db.query(DiscoveredResource)

    if status:
        query = query.filter(DiscoveredResource.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (DiscoveredResource.title.ilike(search_term)) |
            (DiscoveredResource.summary.ilike(search_term)) |
            (DiscoveredResource.source.ilike(search_term))
        )

    # Get counts
    total_all = db.query(func.count(DiscoveredResource.id)).scalar() or 0
    total_pending = db.query(func.count(DiscoveredResource.id)).filter(
        DiscoveredResource.status == "pending_review"
    ).scalar() or 0
    total_approved = db.query(func.count(DiscoveredResource.id)).filter(
        DiscoveredResource.status == "approved"
    ).scalar() or 0
    total_rejected = db.query(func.count(DiscoveredResource.id)).filter(
        DiscoveredResource.status == "rejected"
    ).scalar() or 0

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    resources = query.order_by(
        desc(DiscoveredResource.discovered_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/resources.html",
        {
            "request": request,
            "user": user,
            "resources": resources,
            "current_status": status,
            "search": search,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "counts": {
                "all": total_all,
                "pending_review": total_pending,
                "approved": total_approved,
                "rejected": total_rejected
            },
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


@router.get("/resources/{resource_id}", response_class=HTMLResponse)
async def discovery_resource_detail(
    resource_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Resource detail view."""
    resource = db.query(DiscoveredResource).filter(DiscoveredResource.id == resource_id).first()

    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/resource_detail.html",
        {
            "request": request,
            "user": user,
            "resource": resource,
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


@router.post("/resources/{resource_id}/approve")
async def approve_resource(
    resource_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a discovered resource."""
    resource = db.query(DiscoveredResource).filter(DiscoveredResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource.status = "approved"
    resource.reviewed_by = user.id
    resource.reviewed_at = datetime.now(timezone.utc)
    resource.review_notes = notes
    db.commit()

    return RedirectResponse(url=f"/admin/discovery/resources/{resource_id}", status_code=303)


@router.post("/resources/{resource_id}/reject")
async def reject_resource(
    resource_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject a discovered resource."""
    resource = db.query(DiscoveredResource).filter(DiscoveredResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource.status = "rejected"
    resource.reviewed_by = user.id
    resource.reviewed_at = datetime.now(timezone.utc)
    resource.review_notes = notes
    db.commit()

    return RedirectResponse(url=f"/admin/discovery/resources/{resource_id}", status_code=303)


@router.post("/api/resources")
async def add_resource_manually(
    title: str = Form(...),
    url: str = Form(...),
    summary: str = Form(""),
    source: str = Form(""),
    resource_type: str = Form("article"),
    author: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Manually add a discovered resource."""
    from app.services.discovery.dedup import extract_domain

    existing_slugs = {r.slug for r in db.query(DiscoveredResource.slug).all()}

    resource = DiscoveredResource(
        title=title,
        slug=generate_resource_slug(title, existing_slugs),
        url=url,
        url_domain=extract_domain(url),
        summary=summary,
        source=source,
        resource_type=resource_type,
        author=author if author else None,
        source_type="manual",
        source_url=url,
        status="pending_review",
        confidence_score=1.0
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    return {"status": "success", "resource_id": str(resource.id), "slug": resource.slug}


# ============================================================================
# USE CASES ROUTES
# ============================================================================

def generate_usecase_slug(title: str, existing_slugs: set[str] | None = None) -> str:
    """Generate a URL-friendly slug from use case title."""
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')
    slug = slug[:80]

    if existing_slugs:
        base_slug = slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}-{counter}"
            counter += 1

    return slug


@router.get("/use-cases", response_class=HTMLResponse)
async def discovery_usecases_list(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List discovered use cases."""
    per_page = 50

    query = db.query(UseCase)

    if status:
        query = query.filter(UseCase.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (UseCase.title.ilike(search_term)) |
            (UseCase.summary.ilike(search_term)) |
            (UseCase.organization.ilike(search_term))
        )

    # Get counts
    total_all = db.query(func.count(UseCase.id)).scalar() or 0
    total_pending = db.query(func.count(UseCase.id)).filter(
        UseCase.status == "pending_review"
    ).scalar() or 0
    total_approved = db.query(func.count(UseCase.id)).filter(
        UseCase.status == "approved"
    ).scalar() or 0
    total_rejected = db.query(func.count(UseCase.id)).filter(
        UseCase.status == "rejected"
    ).scalar() or 0

    total = query.count()
    total_pages = (total + per_page - 1) // per_page

    usecases = query.order_by(
        desc(UseCase.discovered_at)
    ).offset((page - 1) * per_page).limit(per_page).all()

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/usecases.html",
        {
            "request": request,
            "user": user,
            "usecases": usecases,
            "current_status": status,
            "search": search,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "counts": {
                "all": total_all,
                "pending_review": total_pending,
                "approved": total_approved,
                "rejected": total_rejected
            },
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


@router.get("/use-cases/{usecase_id}", response_class=HTMLResponse)
async def discovery_usecase_detail(
    usecase_id: str,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Use case detail view."""
    usecase = db.query(UseCase).filter(UseCase.id == usecase_id).first()

    if not usecase:
        raise HTTPException(status_code=404, detail="Use case not found")

    admin_context = get_admin_context_dict(request)
    return templates.TemplateResponse(
        "admin/discovery/usecase_detail.html",
        {
            "request": request,
            "user": user,
            "usecase": usecase,
            **admin_context,
            "active_admin_page": "discovery",
        }
    )


@router.post("/use-cases/{usecase_id}/approve")
async def approve_usecase(
    usecase_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Approve a discovered use case."""
    usecase = db.query(UseCase).filter(UseCase.id == usecase_id).first()
    if not usecase:
        raise HTTPException(status_code=404, detail="Use case not found")

    usecase.status = "approved"
    usecase.reviewed_by = user.id
    usecase.reviewed_at = datetime.now(timezone.utc)
    usecase.review_notes = notes
    db.commit()

    return RedirectResponse(url=f"/admin/discovery/use-cases/{usecase_id}", status_code=303)


@router.post("/use-cases/{usecase_id}/reject")
async def reject_usecase(
    usecase_id: str,
    notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Reject a discovered use case."""
    usecase = db.query(UseCase).filter(UseCase.id == usecase_id).first()
    if not usecase:
        raise HTTPException(status_code=404, detail="Use case not found")

    usecase.status = "rejected"
    usecase.reviewed_by = user.id
    usecase.reviewed_at = datetime.now(timezone.utc)
    usecase.review_notes = notes
    db.commit()

    return RedirectResponse(url=f"/admin/discovery/use-cases/{usecase_id}", status_code=303)


@router.post("/api/use-cases")
async def add_usecase_manually(
    title: str = Form(...),
    organization: str = Form(""),
    country: str = Form(""),
    organization_type: str = Form(""),
    summary: str = Form(""),
    challenge: str = Form(""),
    solution: str = Form(""),
    outcome: str = Form(""),
    lessons_learned: str = Form(""),
    source_url: str = Form(""),
    source_name: str = Form(""),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Manually add a use case."""
    existing_slugs = {u.slug for u in db.query(UseCase.slug).all()}

    usecase = UseCase(
        title=title,
        slug=generate_usecase_slug(title, existing_slugs),
        organization=organization if organization else None,
        country=country if country else None,
        organization_type=organization_type if organization_type else None,
        summary=summary if summary else None,
        challenge=challenge if challenge else None,
        solution=solution if solution else None,
        outcome=outcome if outcome else None,
        lessons_learned=lessons_learned if lessons_learned else None,
        source_url=source_url if source_url else None,
        source_name=source_name if source_name else None,
        source_type="manual",
        status="pending_review",
        confidence_score=1.0
    )

    db.add(usecase)
    db.commit()
    db.refresh(usecase)

    return {"status": "success", "usecase_id": str(usecase.id), "slug": usecase.slug}
