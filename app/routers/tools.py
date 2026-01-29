"""Tool listing, detail, and finder routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.toolkit import UserActivity
from app.dependencies import get_current_user
from app.services.kit_loader import (
    get_all_tools, get_tool, get_all_clusters,
    get_cluster_tools, search_tools
)
from app.templates_engine import templates


router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("/finder", response_class=HTMLResponse)
async def tool_finder(
    request: Request,
    need: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Interactive tool finder to help journalists choose the right tool."""
    clusters = get_all_clusters()
    all_tools_list = get_all_tools()

    # Pre-defined journalism needs mapped to use case groups
    needs_map = {
        "transcribe": {"label": "Transcribe interviews or audio", "use_cases": ["transcription"], "clusters": ["transcription-translation"]},
        "translate": {"label": "Translate content between languages", "use_cases": ["translation"], "clusters": ["transcription-translation"]},
        "verify": {"label": "Verify images, video or claims", "use_cases": ["verification"], "clusters": ["verification-investigations"]},
        "investigate": {"label": "Investigate documents or data", "use_cases": ["document-research", "network-analysis"], "clusters": ["verification-investigations"]},
        "monitor": {"label": "Monitor websites for changes", "use_cases": ["web-monitoring"], "clusters": ["verification-investigations"]},
        "write": {"label": "Draft, edit or summarise text", "use_cases": ["llm-writing", "text-editing"], "clusters": ["writing-analysis"]},
        "data": {"label": "Analyse data or documents", "use_cases": ["data-analysis"], "clusters": ["writing-analysis"]},
        "video": {"label": "Create or edit video content", "use_cases": ["video-production"], "clusters": ["audio-video-social"]},
        "audio": {"label": "Create audio or voice content", "use_cases": ["audio-voice"], "clusters": ["audio-video-social"]},
        "images": {"label": "Generate or edit images", "use_cases": ["image-generation"], "clusters": ["audio-video-social"]},
        "social": {"label": "Manage social media", "use_cases": ["social-media"], "clusters": ["audio-video-social"]},
        "security": {"label": "Protect sources and data", "use_cases": ["security-privacy"], "clusters": ["security-challenges"]},
        "build": {"label": "Build custom tools or apps", "use_cases": ["coding-building"], "clusters": ["building-your-own-tools"]},
        "automate": {"label": "Automate workflows", "use_cases": ["automation"], "clusters": ["ai-agents-automated-workflows"]},
        "sovereign": {"label": "Use only sovereign/local tools", "use_cases": ["local-ai"], "clusters": []},
    }

    recommended = []
    selected_need = None

    if need and need in needs_map:
        selected_need = needs_map[need]
        target_use_cases = set(selected_need["use_cases"])
        target_clusters = set(selected_need["clusters"])

        for tool in all_tools_list:
            cr = tool.get("cross_references", {})
            tool_use_cases = set(cr.get("use_cases", []))

            # Match by use case or cluster
            if tool_use_cases & target_use_cases:
                recommended.append(tool)
            elif tool.get("cluster_slug") in target_clusters and tool not in recommended:
                recommended.append(tool)

        # Special case: sovereign filter
        if need == "sovereign":
            recommended = [t for t in all_tools_list if t.get("cdi_scores", {}).get("invasiveness", 10) == 0]

        # Sort: lower total CDI score first (easier, cheaper, less invasive)
        recommended.sort(key=lambda t: (
            t["cdi_scores"]["cost"] + t["cdi_scores"]["difficulty"] + t["cdi_scores"]["invasiveness"]
        ))

    # Log activity if user is authenticated and a need was selected
    if user and need and need in needs_map:
        activity = UserActivity(
            user_id=user.id,
            activity_type="tool_finder",
            query=needs_map[need]["label"],
            details={"need": need, "results_count": len(recommended)},
        )
        db.add(activity)
        db.commit()

    # Get personalized picks for logged-in users
    personalized_picks = []
    show_personalized = False
    if user and need and need in needs_map:
        try:
            from app.services.recommendation import get_recommendations
            # Get recommendations filtered by the selected use case
            use_case = needs_map[need]["use_cases"][0] if needs_map[need]["use_cases"] else None
            recs = get_recommendations(db, user, use_case=use_case, limit=3)
            # Convert Pydantic models to dicts for Jinja2
            personalized_picks = [r.model_dump() if hasattr(r, 'model_dump') else r for r in recs]
            show_personalized = len(personalized_picks) > 0
        except Exception:
            pass  # Fail gracefully

    return templates.TemplateResponse(
        "tools/finder.html",
        {
            "request": request,
            "user": user,
            "needs": needs_map,
            "selected_need": need,
            "selected_need_info": selected_need,
            "recommended": recommended,
            "clusters": clusters,
            "suggested_tools": personalized_picks,
            "suggested_title": "Personalized Picks",
            "show_suggested": show_personalized,
            "suggested_location": "finder",
        }
    )


@router.get("/cdi", response_class=HTMLResponse)
async def cdi_explorer(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Interactive CDI score explorer — scatter chart, sliders, comparisons."""
    import json as json_mod
    all_tools_list = get_all_tools()
    clusters = get_all_clusters()

    # Prepare tools data for client-side JS
    tools_json = json_mod.dumps([
        {
            "slug": t["slug"],
            "name": t["name"],
            "cluster_name": t.get("cluster_name", ""),
            "cluster_slug": t.get("cluster_slug", ""),
            "cost": t["cdi_scores"]["cost"],
            "difficulty": t["cdi_scores"]["difficulty"],
            "invasiveness": t["cdi_scores"]["invasiveness"],
            "total": t["cdi_scores"]["cost"] + t["cdi_scores"]["difficulty"] + t["cdi_scores"]["invasiveness"],
            "purpose": t.get("purpose", ""),
            "tags": t.get("tags", []),
        }
        for t in all_tools_list
    ])

    return templates.TemplateResponse(
        "tools/cdi.html",
        {
            "request": request,
            "user": user,
            "tools_json": tools_json,
            "tool_count": len(all_tools_list),
            "clusters": clusters,
        }
    )


@router.get("", response_class=HTMLResponse)
async def tools_index(
    request: Request,
    cluster: Optional[str] = None,
    q: Optional[str] = None,
    max_cost: Optional[str] = None,
    max_difficulty: Optional[str] = None,
    max_invasiveness: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all tools with optional filtering."""
    clusters = get_all_clusters()

    # Parse optional int params (empty strings from form become None)
    cost_val = int(max_cost) if max_cost and max_cost.isdigit() else None
    diff_val = int(max_difficulty) if max_difficulty and max_difficulty.isdigit() else None
    inv_val = int(max_invasiveness) if max_invasiveness and max_invasiveness.isdigit() else None
    cluster_val = cluster if cluster else None

    tools = search_tools(
        query=q or "",
        cluster_slug=cluster_val,
        max_cost=cost_val,
        max_difficulty=diff_val,
        max_invasiveness=inv_val,
    )

    # Log activity if user is authenticated and a search/filter was used
    if user and (q or cluster_val or cost_val is not None or diff_val is not None or inv_val is not None):
        details = {"results_count": len(tools)}
        if cluster_val:
            details["cluster"] = cluster_val
        if cost_val is not None:
            details["max_cost"] = cost_val
        if diff_val is not None:
            details["max_difficulty"] = diff_val
        if inv_val is not None:
            details["max_invasiveness"] = inv_val
        activity = UserActivity(
            user_id=user.id,
            activity_type="tool_search",
            query=q or None,
            details=details,
        )
        db.add(activity)
        db.commit()

    return templates.TemplateResponse(
        "tools/index.html",
        {
            "request": request,
            "user": user,
            "tools": tools,
            "clusters": clusters,
            "cluster": cluster_val,
            "q": q or "",
            "max_cost": cost_val,
            "max_difficulty": diff_val,
            "max_invasiveness": inv_val,
            "total_tools": len(get_all_tools()),
        }
    )


@router.get("/{slug}", response_class=HTMLResponse)
async def tool_detail(
    request: Request,
    slug: str,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Show individual tool detail page with cross-references."""
    tool = get_tool(slug)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Get related tools from same cluster
    related = [
        t for t in get_cluster_tools(tool.get("cluster_slug", ""))
        if t["slug"] != slug
    ]

    # Resolve cross-references
    cross_refs = tool.get("cross_references", {})

    # Sovereign alternative (if this tool has one)
    sovereign_alt = None
    sov_slug = cross_refs.get("sovereign_alternative")
    if sov_slug:
        sovereign_alt = get_tool(sov_slug)

    # Tools this is a sovereign alternative FOR
    sovereign_for_tools = []
    for s in cross_refs.get("sovereign_alternative_for", []):
        t = get_tool(s)
        if t:
            sovereign_for_tools.append(t)

    # Similar tools
    similar_tools = []
    for s in cross_refs.get("similar_tools", []):
        t = get_tool(s)
        if t:
            similar_tools.append(t)

    # Get personalized guidance for logged-in users
    tool_guidance = None
    if user:
        try:
            from app.services.recommendation import get_tool_guidance
            result = get_tool_guidance(db, user, slug)
            if result:
                score, explanation, guidance, citations = result
                # Convert to dict for Jinja2 template
                tool_guidance = {
                    "fit_score": score,
                    "explanation": explanation,
                    "guidance": guidance.model_dump() if hasattr(guidance, 'model_dump') else guidance,
                    "citations": [c.model_dump() if hasattr(c, 'model_dump') else c for c in citations],
                }
        except Exception:
            pass  # Fail gracefully

    # Get playbook for this tool (if published)
    playbook = None
    try:
        from app.models.playbook import ToolPlaybook
        playbook = db.query(ToolPlaybook).filter(
            ToolPlaybook.kit_tool_slug == slug,
            ToolPlaybook.status == "published"
        ).first()
    except Exception:
        pass  # Fail gracefully

    # Log tool view activity
    if user:
        activity = UserActivity(
            user_id=user.id,
            activity_type="tool_view",
            details={"tool_slug": slug, "tool_name": tool.get("name")},
        )
        db.add(activity)
        db.commit()

    return templates.TemplateResponse(
        "tools/detail.html",
        {
            "request": request,
            "user": user,
            "tool": tool,
            "related_tools": related,
            "sovereign_alt": sovereign_alt,
            "sovereign_for_tools": sovereign_for_tools,
            "similar_tools": similar_tools,
            "tool_guidance": tool_guidance,
            "playbook": playbook,
        }
    )
