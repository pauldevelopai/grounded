"""Personalized recommendations API endpoints and pages."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.dependencies import get_current_user, require_user
from app.services.recommendation import (
    get_recommendations,
    get_tool_guidance,
    get_suggested_for_location,
    build_user_context,
    MAX_RECOMMENDATIONS,
)
from app.services.kit_loader import get_tool, get_all_clusters
from app.schemas.recommendation import (
    RecommendationsResponse,
    ToolGuidanceResponse,
    SuggestedBlockResponse,
)
from app.products.guards import require_feature
from app.templates_engine import templates


# HTML page router (no prefix - mounted at root)
page_router = APIRouter(tags=["recommendations-pages"])


import logging
logger = logging.getLogger(__name__)

@page_router.get("/for-you", response_class=HTMLResponse)
async def for_you_page(
    request: Request,
    use_case: Optional[str] = Query(None, description="Filter by use case"),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Dedicated page for personalized tool suggestions."""
    logger.info(f"For You page: user={user.email if user else 'anonymous'}, use_case={use_case}")

    # If not logged in, show login prompt
    if not user:
        return templates.TemplateResponse(
            "recommendations/for_you.html",
            {
                "request": request,
                "user": None,
                "suggested_tools": [],
                "show_suggested": False,
                "requires_login": True,
                "feature_name": "Personalized Recommendations",
                "feature_description": "Get AI tool recommendations tailored to your experience level, budget, and use cases.",
                "clusters": get_all_clusters(),
                "selected_use_case": use_case,
            }
        )

    # Get recommendations for logged-in user (max 8, with rotation tracking)
    recommendations = get_recommendations(
        db=db,
        user=user,
        use_case=use_case,
        limit=MAX_RECOMMENDATIONS,
        record_shown=True,  # Track for rotation
    )
    logger.info(f"Got {len(recommendations)} recommendations for use_case={use_case}")

    # Convert to dicts for template
    suggested_tools = [r.model_dump() if hasattr(r, 'model_dump') else r for r in recommendations]
    logger.info(f"Converted to {len(suggested_tools)} suggested_tools")

    # Build user context summary
    context = build_user_context(db, user)
    context_summary = {
        "budget": context.budget,
        "experience_level": context.ai_experience_level,
        "data_sensitivity": context.data_sensitivity,
        "use_cases": context.use_cases[:5] if context.use_cases else [],
        "constraints": {
            "max_cost": context.max_cost,
            "max_difficulty": context.max_difficulty,
            "max_invasiveness": context.max_invasiveness,
        },
        # Activity signals for transparency
        "searched_queries": context.searched_queries[:3] if context.searched_queries else [],
        "browsed_clusters": context.browsed_clusters[:3] if context.browsed_clusters else [],
        "viewed_tools": context.viewed_tools[:5] if context.viewed_tools else [],
    }
    logger.info(f"User context: budget={context.budget}, exp={context.ai_experience_level}, activity={len(context.searched_queries)} searches, {len(context.browsed_clusters)} clusters")

    # Get clusters for use case filtering
    clusters = get_all_clusters()

    return templates.TemplateResponse(
        "recommendations/for_you.html",
        {
            "request": request,
            "user": user,
            "suggested_tools": suggested_tools,
            "show_suggested": len(suggested_tools) > 0,
            "suggested_title": "Recommended for You",
            "suggested_location": "for_you",
            "user_context": context_summary,
            "clusters": clusters,
            "selected_use_case": use_case,
            "requires_login": False,
        }
    )


# API router (with /api/recommendations prefix)
router = APIRouter(
    prefix="/api/recommendations",
    tags=["recommendations"],
    dependencies=[Depends(require_feature("recommendations"))]  # All recommendation routes require feature
)


@router.get("/for-me", response_model=RecommendationsResponse)
async def get_recommendations_for_me(
    query: Optional[str] = Query(None, description="Search query to filter tools"),
    use_case: Optional[str] = Query(None, description="Use case to filter by"),
    limit: int = Query(MAX_RECOMMENDATIONS, ge=1, le=MAX_RECOMMENDATIONS, description="Maximum recommendations"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get personalized tool recommendations based on user profile and activity.

    Returns tools scored and ranked for this specific user, with explanations
    and citations for why each tool is recommended. Recommendations rotate
    based on user activity and previously shown tools.
    """
    recommendations = get_recommendations(
        db=db,
        user=user,
        query=query,
        use_case=use_case,
        limit=limit,
        record_shown=True,
    )

    # Build summary of user context for transparency
    context = build_user_context(db, user)
    context_summary = {
        "budget": context.budget,
        "experience_level": context.ai_experience_level,
        "data_sensitivity": context.data_sensitivity,
        "use_cases": context.use_cases[:3] if context.use_cases else [],
        "constraints": {
            "max_cost": context.max_cost,
            "max_difficulty": context.max_difficulty,
            "max_invasiveness": context.max_invasiveness,
        },
    }

    return RecommendationsResponse(
        recommendations=recommendations,
        user_context_summary=context_summary,
        query=query,
        use_case=use_case,
    )


@router.get("/for-tool/{slug}", response_model=ToolGuidanceResponse)
async def get_guidance_for_tool(
    slug: str,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Get personalized guidance for a specific tool.

    Returns tailored training plan and rollout approach based on user's
    experience level, risk tolerance, and data sensitivity requirements.
    """
    result = get_tool_guidance(db, user, slug)

    if result is None:
        raise HTTPException(status_code=404, detail="Tool not found")

    score, explanation, guidance, citations = result
    tool = get_tool(slug)

    return ToolGuidanceResponse(
        tool_slug=slug,
        tool_name=tool.get("name", slug),
        fit_score=score,
        explanation=explanation,
        guidance=guidance,
        citations=citations,
    )


@router.get("/suggested", response_model=SuggestedBlockResponse)
async def get_suggested_block(
    location: str = Query(..., description="UI location: home, tool_detail, cluster, finder"),
    cluster_slug: Optional[str] = Query(None, description="Current cluster context"),
    tool_slug: Optional[str] = Query(None, description="Current tool context"),
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get suggested tools block for a UI location.

    Returns recommendations formatted for display in the specified location.
    For anonymous users, returns empty block (show_block=False).
    """
    if not user:
        return SuggestedBlockResponse(
            location=location,
            recommendations=[],
            title="",
            show_block=False,
        )

    recommendations = get_suggested_for_location(db, user, location)

    # Customize title based on location
    titles = {
        "home": "Suggested for You",
        "tool_detail": "You Might Also Like",
        "cluster": "Best Fit for You",
        "finder": "Personalized Picks",
    }
    title = titles.get(location, "Suggested for You")

    return SuggestedBlockResponse(
        location=location,
        recommendations=recommendations,
        title=title,
        show_block=len(recommendations) > 0,
    )
