"""Tool listing, detail, and finder routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Request, HTTPException, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.toolkit import UserActivity
from app.dependencies import get_current_user, require_auth_page
from app.middleware.csrf import CSRFProtectionMiddleware
from app.services.kit_loader import (
    get_all_tools, get_tool, get_all_clusters,
    get_cluster_tools, search_tools,
    get_all_tools_with_approved, get_all_clusters_with_approved,
    get_approved_tools_from_db, ADMIN_APPROVED_CLUSTER_SLUG
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
    db: Session = Depends(get_db),
):
    """Interactive CDI score explorer — scatter chart, sliders, comparisons."""
    import json as json_mod
    all_tools_list = get_all_tools_with_approved(db)
    clusters = get_all_clusters_with_approved(db)

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
            "is_admin_approved": t.get("is_admin_approved", False),
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
    """List all tools with optional filtering (includes admin-approved tools)."""
    clusters = get_all_clusters_with_approved(db)

    # Parse optional int params (empty strings from form become None)
    cost_val = int(max_cost) if max_cost and max_cost.isdigit() else None
    diff_val = int(max_difficulty) if max_difficulty and max_difficulty.isdigit() else None
    inv_val = int(max_invasiveness) if max_invasiveness and max_invasiveness.isdigit() else None
    cluster_val = cluster if cluster else None

    # Get kit tools
    tools = search_tools(
        query=q or "",
        cluster_slug=cluster_val,
        max_cost=cost_val,
        max_difficulty=diff_val,
        max_invasiveness=inv_val,
    )

    # Include admin-approved tools in search
    approved_tools = get_approved_tools_from_db(db)
    if cluster_val == ADMIN_APPROVED_CLUSTER_SLUG:
        # Filter to only approved tools
        tools = approved_tools
    elif not cluster_val:
        # No cluster filter - include all approved tools
        # Apply same search/filter criteria
        if q:
            q_lower = q.lower()
            approved_tools = [
                t for t in approved_tools
                if q_lower in t.get("name", "").lower()
                or q_lower in t.get("description", "").lower()
                or any(q_lower in tag.lower() for tag in t.get("tags", []))
            ]
        if cost_val is not None:
            approved_tools = [t for t in approved_tools if t["cdi_scores"]["cost"] <= cost_val]
        if diff_val is not None:
            approved_tools = [t for t in approved_tools if t["cdi_scores"]["difficulty"] <= diff_val]
        if inv_val is not None:
            approved_tools = [t for t in approved_tools if t["cdi_scores"]["invasiveness"] <= inv_val]
        tools = tools + approved_tools

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

    all_tools_count = len(get_all_tools()) + len(get_approved_tools_from_db(db))

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
            "total_tools": all_tools_count,
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

    # If not in kit, check admin-approved tools
    if not tool:
        approved_tools = get_approved_tools_from_db(db)
        tool = next((t for t in approved_tools if t["slug"] == slug), None)

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Get related tools from same cluster
    if tool.get("cluster_slug") == ADMIN_APPROVED_CLUSTER_SLUG:
        # For admin-approved tools, show other approved tools
        related = [
            t for t in get_approved_tools_from_db(db)
            if t["slug"] != slug
        ][:5]  # Limit to 5
    else:
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


@router.get("/suggest", response_class=HTMLResponse)
async def suggest_tool_form(
    request: Request,
    response: Response,
    success: Optional[str] = None,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Show the tool suggestion form for logged-in users."""
    csrf_token = CSRFProtectionMiddleware.generate_token()

    template_response = templates.TemplateResponse(
        "tools/suggest.html",
        {
            "request": request,
            "user": user,
            "csrf_token": csrf_token,
            "success": success,
        }
    )
    CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
    return template_response


@router.post("/suggest")
async def suggest_tool(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    description: str = Form(""),
    why_valuable: str = Form(""),
    use_cases: str = Form(""),
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Submit a tool suggestion for admin review."""
    from app.models.tool_suggestion import ToolSuggestion

    # Validate URL format (basic check)
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    suggestion = ToolSuggestion(
        name=name.strip(),
        url=url.strip(),
        description=description.strip() if description else None,
        why_valuable=why_valuable.strip() if why_valuable else None,
        use_cases=use_cases.strip() if use_cases else None,
        submitted_by=user.id,
    )

    db.add(suggestion)
    db.commit()

    # Log activity
    activity = UserActivity(
        user_id=user.id,
        activity_type="tool_suggested",
        details={"tool_name": name, "tool_url": url},
    )
    db.add(activity)
    db.commit()

    return RedirectResponse(url="/tools/suggest?success=1", status_code=303)


# ============================================================================
# Learning Profile Activity Tracking Endpoints
# ============================================================================

@router.post("/track/time-spent")
async def track_time_spent(
    request: Request,
    tool_slug: str = Form(...),
    duration_seconds: int = Form(...),
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Track time spent on a tool detail page (called via JS beacon)."""
    from app.services.learning_profile import track_tool_interaction

    # Validate duration (minimum 5 seconds, max 30 minutes)
    if duration_seconds < 5:
        return {"status": "ignored", "reason": "duration too short"}
    if duration_seconds > 1800:
        duration_seconds = 1800  # Cap at 30 minutes

    track_tool_interaction(
        db=db,
        user_id=str(user.id),
        tool_slug=tool_slug,
        interaction_type="time_spent",
        details={"duration_seconds": duration_seconds}
    )

    return {"status": "ok"}


@router.post("/track/dismiss")
async def track_dismiss(
    request: Request,
    tool_slug: str = Form(...),
    context: str = Form("recommendation"),  # where the dismissal happened
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Track when a user dismisses a tool recommendation."""
    from app.services.learning_profile import track_tool_interaction

    track_tool_interaction(
        db=db,
        user_id=str(user.id),
        tool_slug=tool_slug,
        interaction_type="dismissed",
        details={"context": context}
    )

    return {"status": "ok"}


@router.post("/track/favorite")
async def track_favorite(
    request: Request,
    tool_slug: str = Form(...),
    action: str = Form("add"),  # "add" or "remove"
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Track when a user favorites or unfavorites a tool."""
    from app.services.learning_profile import track_tool_interaction

    interaction_type = "favorited" if action == "add" else "unfavorited"

    track_tool_interaction(
        db=db,
        user_id=str(user.id),
        tool_slug=tool_slug,
        interaction_type=interaction_type,
        details={"action": action}
    )

    return {"status": "ok", "action": action}
