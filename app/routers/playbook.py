"""Playbook routes for newsroom implementation guidance.

All endpoints are admin-only.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.db import get_db
from app.dependencies import require_admin
from app.models.auth import User
from app.models import DiscoveredTool, ToolPlaybook, PlaybookSource
from app.services.playbook.pipeline import (
    generate_playbook,
    add_sources_to_playbook,
    get_playbook_with_sources,
)
from app.settings import settings
from app.templates_engine import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/playbooks", tags=["playbooks"])


# ============================================================================
# ADMIN HTML PAGES
# ============================================================================

@router.get("", response_class=HTMLResponse)
async def playbooks_list_page(
    request: Request,
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: List all playbooks."""
    per_page = 20

    # Base query
    query = db.query(ToolPlaybook)

    # Apply filters
    if status:
        query = query.filter(ToolPlaybook.status == status)

    if search:
        # Search in related tool name
        query = query.join(DiscoveredTool, ToolPlaybook.discovered_tool_id == DiscoveredTool.id)
        query = query.filter(DiscoveredTool.name.ilike(f"%{search}%"))

    # Get counts by status
    status_counts = {
        "all": db.query(ToolPlaybook).count(),
        "draft": db.query(ToolPlaybook).filter(ToolPlaybook.status == "draft").count(),
        "generating": db.query(ToolPlaybook).filter(ToolPlaybook.status == "generating").count(),
        "published": db.query(ToolPlaybook).filter(ToolPlaybook.status == "published").count(),
        "archived": db.query(ToolPlaybook).filter(ToolPlaybook.status == "archived").count(),
    }

    # Paginate
    total = query.count()
    playbooks = (
        query
        .order_by(desc(ToolPlaybook.updated_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    total_pages = (total + per_page - 1) // per_page

    return templates.TemplateResponse(
        "admin/playbooks/index.html",
        {
            "request": request,
            "user": user,
            "playbooks": playbooks,
            "status_counts": status_counts,
            "current_status": status,
            "search": search,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        }
    )


@router.get("/tool/{tool_id}", response_class=HTMLResponse)
async def playbook_for_tool_page(
    request: Request,
    tool_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: View/create playbook for a specific discovered tool."""
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Check for existing playbook
    playbook = db.query(ToolPlaybook).filter(
        ToolPlaybook.discovered_tool_id == tool_id
    ).first()

    sources = []
    if playbook:
        sources = db.query(PlaybookSource).filter(
            PlaybookSource.playbook_id == playbook.id
        ).order_by(PlaybookSource.is_primary.desc(), PlaybookSource.created_at).all()

    return templates.TemplateResponse(
        "admin/playbooks/tool_detail.html",
        {
            "request": request,
            "user": user,
            "tool": tool,
            "playbook": playbook,
            "sources": sources,
        }
    )


@router.get("/{playbook_id}", response_class=HTMLResponse)
async def playbook_detail_page(
    request: Request,
    playbook_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: View playbook details."""
    data = get_playbook_with_sources(db, playbook_id)

    if not data:
        raise HTTPException(status_code=404, detail="Playbook not found")

    return templates.TemplateResponse(
        "admin/playbooks/detail.html",
        {
            "request": request,
            "user": user,
            "playbook": data["playbook"],
            "sources": data["sources"],
            "tool": data["tool"],
        }
    )


@router.get("/{playbook_id}/edit", response_class=HTMLResponse)
async def playbook_edit_page(
    request: Request,
    playbook_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: Edit playbook content."""
    data = get_playbook_with_sources(db, playbook_id)

    if not data:
        raise HTTPException(status_code=404, detail="Playbook not found")

    return templates.TemplateResponse(
        "admin/playbooks/edit.html",
        {
            "request": request,
            "user": user,
            "playbook": data["playbook"],
            "sources": data["sources"],
            "tool": data["tool"],
        }
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/generate/{tool_id}")
async def trigger_playbook_generation(
    tool_id: str,
    regenerate: bool = Query(False, description="Regenerate even if exists"),
    max_sources: int = Query(10, ge=1, le=20),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Generate a playbook for a discovered tool.

    This scrapes the tool's website and related pages, then uses LLM
    to extract newsroom-relevant guidance.
    """
    tool = db.query(DiscoveredTool).filter(DiscoveredTool.id == tool_id).first()

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    try:
        playbook = await generate_playbook(
            db=db,
            tool_id=tool_id,
            max_sources=max_sources,
            regenerate=regenerate,
        )

        return {
            "status": "success",
            "playbook_id": str(playbook.id),
            "tool_name": tool.name,
            "source_count": playbook.source_count,
            "playbook_status": playbook.status,
        }

    except Exception as e:
        logger.error(f"Playbook generation failed for {tool.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_id}/add-sources")
async def add_sources(
    playbook_id: str,
    urls: str = Form(..., description="Newline-separated URLs"),
    source_type: str = Form("official_docs"),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Add additional sources to a playbook."""
    playbook = db.query(ToolPlaybook).filter(ToolPlaybook.id == playbook_id).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Parse URLs
    url_list = [u.strip() for u in urls.split("\n") if u.strip()]

    if not url_list:
        raise HTTPException(status_code=400, detail="No valid URLs provided")

    try:
        sources = await add_sources_to_playbook(
            db=db,
            playbook_id=playbook_id,
            urls=url_list,
            source_type=source_type,
        )

        return {
            "status": "success",
            "sources_added": len(sources),
            "playbook_id": playbook_id,
        }

    except Exception as e:
        logger.error(f"Failed to add sources: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{playbook_id}/update")
async def update_playbook(
    playbook_id: str,
    best_use_cases: Optional[str] = Form(None),
    implementation_steps: Optional[str] = Form(None),
    common_mistakes: Optional[str] = Form(None),
    privacy_notes: Optional[str] = Form(None),
    replaces_improves: Optional[str] = Form(None),
    pricing_summary: Optional[str] = Form(None),
    integration_notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update playbook content manually."""
    playbook = db.query(ToolPlaybook).filter(ToolPlaybook.id == playbook_id).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Update fields
    if best_use_cases is not None:
        playbook.best_use_cases = best_use_cases or None
    if implementation_steps is not None:
        playbook.implementation_steps = implementation_steps or None
    if common_mistakes is not None:
        playbook.common_mistakes = common_mistakes or None
    if privacy_notes is not None:
        playbook.privacy_notes = privacy_notes or None
    if replaces_improves is not None:
        playbook.replaces_improves = replaces_improves or None
    if pricing_summary is not None:
        playbook.pricing_summary = pricing_summary or None
    if integration_notes is not None:
        playbook.integration_notes = integration_notes or None

    playbook.updated_at = datetime.now(timezone.utc)

    db.commit()

    return RedirectResponse(
        url=f"/admin/playbooks/{playbook_id}",
        status_code=303
    )


@router.post("/{playbook_id}/status")
async def update_playbook_status(
    playbook_id: str,
    status: str = Form(...),
    review_notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update playbook status (publish, archive, etc.)."""
    playbook = db.query(ToolPlaybook).filter(ToolPlaybook.id == playbook_id).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    valid_statuses = ["draft", "published", "archived"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    playbook.status = status
    playbook.reviewed_by = user.id
    playbook.reviewed_at = datetime.now(timezone.utc)

    if review_notes:
        playbook.review_notes = review_notes

    db.commit()

    return RedirectResponse(
        url=f"/admin/playbooks/{playbook_id}",
        status_code=303
    )


@router.delete("/{playbook_id}")
async def delete_playbook(
    playbook_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a playbook."""
    playbook = db.query(ToolPlaybook).filter(ToolPlaybook.id == playbook_id).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    tool_id = playbook.discovered_tool_id
    db.delete(playbook)
    db.commit()

    return {
        "status": "success",
        "message": "Playbook deleted",
        "tool_id": str(tool_id) if tool_id else None,
    }


@router.get("/api/list")
async def list_playbooks_api(
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """API endpoint: List playbooks."""
    query = db.query(ToolPlaybook)

    if status:
        query = query.filter(ToolPlaybook.status == status)

    total = query.count()
    playbooks = (
        query
        .order_by(desc(ToolPlaybook.updated_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "playbooks": [
            {
                "id": str(p.id),
                "discovered_tool_id": str(p.discovered_tool_id) if p.discovered_tool_id else None,
                "kit_tool_slug": p.kit_tool_slug,
                "tool_name": p.discovered_tool.name if p.discovered_tool else p.kit_tool_slug,
                "status": p.status,
                "source_count": p.source_count,
                "has_use_cases": bool(p.best_use_cases),
                "has_steps": bool(p.implementation_steps),
                "generated_at": p.generated_at.isoformat() if p.generated_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p in playbooks
        ]
    }


@router.get("/api/{playbook_id}")
async def get_playbook_api(
    playbook_id: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """API endpoint: Get playbook details."""
    data = get_playbook_with_sources(db, playbook_id)

    if not data:
        raise HTTPException(status_code=404, detail="Playbook not found")

    playbook = data["playbook"]
    sources = data["sources"]
    tool = data["tool"]

    return {
        "id": str(playbook.id),
        "tool": {
            "id": str(tool.id) if tool else None,
            "name": tool.name if tool else None,
            "url": tool.url if tool else None,
        },
        "status": playbook.status,
        "best_use_cases": playbook.best_use_cases,
        "implementation_steps": playbook.implementation_steps,
        "common_mistakes": playbook.common_mistakes,
        "privacy_notes": playbook.privacy_notes,
        "replaces_improves": playbook.replaces_improves,
        "key_features": playbook.key_features,
        "pricing_summary": playbook.pricing_summary,
        "integration_notes": playbook.integration_notes,
        "source_count": playbook.source_count,
        "sources": [
            {
                "id": str(s.id),
                "url": s.url,
                "title": s.title,
                "source_type": s.source_type,
                "is_primary": s.is_primary,
                "scrape_status": s.scrape_status,
                "contributed_sections": s.contributed_sections,
            }
            for s in sources
        ],
        "generation_model": playbook.generation_model,
        "generated_at": playbook.generated_at.isoformat() if playbook.generated_at else None,
        "reviewed_at": playbook.reviewed_at.isoformat() if playbook.reviewed_at else None,
    }


# ============================================================================
# KIT TOOLS PLAYBOOK ENDPOINTS
# ============================================================================

@router.get("/kit-tools", response_class=HTMLResponse)
async def kit_tools_playbooks_page(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: List all curated kit tools and their playbook status."""
    from app.services.kit_loader import get_all_tools

    all_tools = get_all_tools()

    # Get playbooks for kit tools
    kit_playbooks = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug.isnot(None)
    ).all()

    playbook_map = {p.kit_tool_slug: p for p in kit_playbooks}

    # Enrich tools with playbook info
    tools_with_status = []
    for tool in all_tools:
        playbook = playbook_map.get(tool["slug"])
        tools_with_status.append({
            "tool": tool,
            "playbook": playbook,
            "has_playbook": playbook is not None,
            "playbook_status": playbook.status if playbook else None,
        })

    # Count stats
    total = len(all_tools)
    with_playbook = len([t for t in tools_with_status if t["has_playbook"]])
    published = len([t for t in tools_with_status if t["playbook_status"] == "published"])

    return templates.TemplateResponse(
        "admin/playbooks/kit_tools.html",
        {
            "request": request,
            "user": user,
            "tools": tools_with_status,
            "total": total,
            "with_playbook": with_playbook,
            "published": published,
        }
    )


@router.get("/kit-tools/{slug}", response_class=HTMLResponse)
async def kit_tool_playbook_page(
    request: Request,
    slug: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Admin page: View/create playbook for a curated kit tool."""
    from app.services.kit_loader import get_tool

    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Check for existing playbook
    playbook = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug == slug
    ).first()

    sources = []
    if playbook:
        sources = db.query(PlaybookSource).filter(
            PlaybookSource.playbook_id == playbook.id
        ).order_by(PlaybookSource.is_primary.desc(), PlaybookSource.created_at).all()

    return templates.TemplateResponse(
        "admin/playbooks/kit_tool_detail.html",
        {
            "request": request,
            "user": user,
            "tool": tool,
            "playbook": playbook,
            "sources": sources,
        }
    )


@router.post("/kit-tools/{slug}/create")
async def create_kit_tool_playbook(
    slug: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new playbook for a curated kit tool."""
    from app.services.kit_loader import get_tool

    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Check if playbook already exists
    existing = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug == slug
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Playbook already exists for this tool")

    # Create new playbook
    playbook = ToolPlaybook(
        kit_tool_slug=slug,
        status="draft",
        source_count=0,
    )
    db.add(playbook)
    db.commit()
    db.refresh(playbook)

    return RedirectResponse(
        url=f"/admin/playbooks/kit-tools/{slug}",
        status_code=303
    )


@router.post("/kit-tools/{slug}/update")
async def update_kit_tool_playbook(
    slug: str,
    best_use_cases: Optional[str] = Form(None),
    implementation_steps: Optional[str] = Form(None),
    common_mistakes: Optional[str] = Form(None),
    privacy_notes: Optional[str] = Form(None),
    replaces_improves: Optional[str] = Form(None),
    pricing_summary: Optional[str] = Form(None),
    integration_notes: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update kit tool playbook content."""
    playbook = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug == slug
    ).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    # Update fields
    if best_use_cases is not None:
        playbook.best_use_cases = best_use_cases or None
    if implementation_steps is not None:
        playbook.implementation_steps = implementation_steps or None
    if common_mistakes is not None:
        playbook.common_mistakes = common_mistakes or None
    if privacy_notes is not None:
        playbook.privacy_notes = privacy_notes or None
    if replaces_improves is not None:
        playbook.replaces_improves = replaces_improves or None
    if pricing_summary is not None:
        playbook.pricing_summary = pricing_summary or None
    if integration_notes is not None:
        playbook.integration_notes = integration_notes or None

    playbook.updated_at = datetime.now(timezone.utc)

    db.commit()

    return RedirectResponse(
        url=f"/admin/playbooks/kit-tools/{slug}",
        status_code=303
    )


@router.post("/kit-tools/{slug}/publish")
async def publish_kit_tool_playbook(
    slug: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Publish a kit tool playbook."""
    playbook = db.query(ToolPlaybook).filter(
        ToolPlaybook.kit_tool_slug == slug
    ).first()

    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found")

    playbook.status = "published"
    playbook.reviewed_by = user.id
    playbook.reviewed_at = datetime.now(timezone.utc)

    db.commit()

    return RedirectResponse(
        url=f"/admin/playbooks/kit-tools/{slug}",
        status_code=303
    )
