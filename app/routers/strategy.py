"""Strategy plan routes."""
from typing import List
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.models.toolkit import StrategyPlan
from app.dependencies import require_auth_page
from app.services.strategy import generate_strategy_plan, export_plan_to_markdown


router = APIRouter(prefix="/strategy", tags=["strategy"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def strategy_wizard(
    request: Request,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    Strategy wizard form page (requires authentication).
    """
    return templates.TemplateResponse(
        "strategy/wizard.html",
        {
            "request": request,
            "user": user
        }
    )


@router.post("/generate", response_class=HTMLResponse)
async def generate_strategy(
    request: Request,
    role: str = Form(...),
    org_type: str = Form(...),
    risk_level: str = Form(...),
    data_sensitivity: str = Form(...),
    budget: str = Form(...),
    deployment_pref: str = Form(...),
    use_cases: List[str] = Form([]),
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db)
):
    """
    Generate strategy plan from wizard inputs.

    Redirects to plan view page.
    """
    # Build inputs dictionary
    inputs = {
        "role": role,
        "org_type": org_type,
        "risk_level": risk_level,
        "data_sensitivity": data_sensitivity,
        "budget": budget,
        "deployment_pref": deployment_pref,
        "use_cases": use_cases
    }

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
