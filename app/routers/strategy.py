"""Strategy plan routes."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.toolkit import StrategyPlan, UserActivity
from app.dependencies import require_auth_page, get_current_user
from app.services.strategy import generate_strategy_plan, export_plan_to_markdown
from app.middleware.csrf import CSRFProtectionMiddleware
from app.templates_engine import templates
from app.products.guards import require_feature


router = APIRouter(
    prefix="/strategy",
    tags=["strategy"],
)


@router.get("", response_class=HTMLResponse)
async def strategy_wizard(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Strategy page - shows profile status and generates from profile.
    Shows login prompt for anonymous users.
    """
    # If not logged in, show login prompt
    if not user:
        return templates.TemplateResponse(
            "strategy/wizard.html",
            {
                "request": request,
                "user": None,
                "csrf_token": "",
                "activity_count": 0,
                "previous_strategies": [],
                "requires_login": True,
                "feature_name": "AI Strategy Builder",
                "feature_description": "Create a personalized AI adoption strategy based on your role, risk tolerance, and use cases.",
            }
        )

    csrf_token = CSRFProtectionMiddleware.generate_token()

    # Count user activities
    activity_count = db.query(UserActivity).filter(
        UserActivity.user_id == user.id
    ).count()

    # Get previous strategies
    previous_strategies = db.query(StrategyPlan).filter(
        StrategyPlan.user_id == user.id
    ).order_by(StrategyPlan.created_at.desc()).limit(5).all()

    template_response = templates.TemplateResponse(
        "strategy/wizard.html",
        {
            "request": request,
            "user": user,
            "csrf_token": csrf_token,
            "activity_count": activity_count,
            "previous_strategies": previous_strategies,
            "requires_login": False,
        }
    )
    CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
    return template_response


@router.post("/generate", response_class=HTMLResponse)
async def generate_strategy(
    request: Request,
    include_activity: bool = Form(False),
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    Generate strategy plan from user profile.
    """
    # Build inputs from user profile (use defaults if not set)
    use_cases = user.use_cases.split(',') if user.use_cases else []
    inputs = {
        "role": user.role,
        "org_type": user.organisation_type,
        "risk_level": user.risk_level,
        "data_sensitivity": user.data_sensitivity,
        "budget": user.budget,
        "deployment_pref": user.deployment_pref,
        "use_cases": use_cases
    }

    # Get activity history if requested
    if include_activity:
        activities = db.query(UserActivity).filter(
            UserActivity.user_id == user.id
        ).order_by(UserActivity.created_at.desc()).limit(50).all()

        if activities:
            tool_searches = [a for a in activities if a.activity_type == 'tool_search']
            tool_finder = [a for a in activities if a.activity_type == 'tool_finder']
            browse_views = [a for a in activities if a.activity_type == 'browse']

            activity_summary = {
                "total_activities": len(activities),
                "tool_searches": [a.query for a in tool_searches if a.query][:10],
                "tool_finder_needs": [a.details.get('need') for a in tool_finder if a.details and a.details.get('need')][:5],
                "browsed_sections": [a.details.get('section') for a in browse_views if a.details and a.details.get('section')][:10]
            }
            inputs["activity_summary"] = activity_summary

    # Generate plan
    try:
        plan = generate_strategy_plan(
            db=db,
            user_id=str(user.id),
            inputs=inputs
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate plan: {str(e)}")

    # Redirect to view page
    return RedirectResponse(url=f"/strategy/{plan.id}", status_code=303)


@router.get("/{plan_id}", response_class=HTMLResponse)
async def view_strategy(
    request: Request,
    plan_id: str,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    View a strategy plan.

    User can only view their own plans.
    """
    # Get plan
    plan = db.query(StrategyPlan).filter(
        StrategyPlan.id == plan_id,
        StrategyPlan.user_id == user.id
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Strategy plan not found")

    return templates.TemplateResponse(
        "strategy/view.html",
        {
            "request": request,
            "user": user,
            "plan": plan
        }
    )


@router.get("/{plan_id}/export")
async def export_strategy(
    plan_id: str,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    Export strategy plan to Markdown file.

    Downloads as .md file.
    """
    # Get plan
    plan = db.query(StrategyPlan).filter(
        StrategyPlan.id == plan_id,
        StrategyPlan.user_id == user.id
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Strategy plan not found")

    # Export to Markdown
    markdown_content = export_plan_to_markdown(plan)

    # Create filename
    filename = f"strategy_plan_{plan.id}.md"

    # Return as downloadable file
    return Response(
        content=markdown_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.post("/{plan_id}/feedback")
async def submit_strategy_feedback(
    request: Request,
    plan_id: str,
    helpful: bool = Form(...),
    implemented_tools: str = Form(""),  # Comma-separated list of tool slugs
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    Submit feedback on a strategy plan.

    This helps the system learn what recommendations work for users.
    """
    from app.services.learning_profile import track_strategy_feedback

    # Verify user owns this plan
    plan = db.query(StrategyPlan).filter(
        StrategyPlan.id == plan_id,
        StrategyPlan.user_id == user.id
    ).first()

    if not plan:
        raise HTTPException(status_code=404, detail="Strategy plan not found")

    # Parse implemented tools list
    tools_list = [t.strip() for t in implemented_tools.split(",") if t.strip()]

    # Track the feedback in learning profile
    track_strategy_feedback(
        db=db,
        user_id=str(user.id),
        strategy_id=str(plan_id),
        helpful=helpful,
        implemented_tools=tools_list
    )

    return {"status": "ok", "message": "Feedback recorded"}
