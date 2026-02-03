"""User profile routes."""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.dependencies import require_auth_page
from app.middleware.csrf import CSRFProtectionMiddleware
from app.templates_engine import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["profile"])


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    response: Response,
    success: Optional[str] = None,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Profile page."""
    csrf_token = CSRFProtectionMiddleware.generate_token()

    # Re-fetch user from current db session to get latest data
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        db_user = user  # Fallback to session user

    template_response = templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": db_user,
            "csrf_token": csrf_token,
            "success": success,
        }
    )
    CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
    return template_response


@router.post("/profile/update")
async def update_profile(
    request: Request,
    display_name: Optional[str] = Form(None),
    organisation: Optional[str] = Form(None),
    organisation_type: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    interests: Optional[str] = Form(None),
    ai_experience_level: Optional[str] = Form(None),
    # Bio and social links
    bio: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    twitter: Optional[str] = Form(None),
    linkedin: Optional[str] = Form(None),
    # Organisation details
    organisation_website: Optional[str] = Form(None),
    organisation_notes: Optional[str] = Form(None),
    # Strategy preference fields
    risk_level: Optional[str] = Form(None),
    data_sensitivity: Optional[str] = Form(None),
    budget: Optional[str] = Form(None),
    deployment_pref: Optional[str] = Form(None),
    use_cases: List[str] = Form([]),
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Update user profile including strategy preferences."""
    logger.info(f"Updating profile for user {user.id}")
    logger.info(f"Form data: display_name={display_name}, role={role}, organisation={organisation}")

    # Re-fetch user in this session to ensure we can update it
    db_user = db.query(User).filter(User.id == user.id).first()
    if not db_user:
        logger.error(f"User {user.id} not found in database")
        return RedirectResponse(url="/login", status_code=303)

    logger.info(f"Found user in db: {db_user.email}")

    # Basic profile fields
    db_user.display_name = display_name.strip() if display_name else None
    db_user.organisation = organisation.strip() if organisation else None
    db_user.organisation_type = organisation_type if organisation_type else None
    db_user.role = role.strip() if role else None
    db_user.country = country.strip() if country else None
    db_user.interests = interests.strip() if interests else None
    db_user.ai_experience_level = ai_experience_level if ai_experience_level else None

    # Bio and social links
    db_user.bio = bio.strip() if bio else None
    db_user.website = website.strip() if website else None
    db_user.twitter = twitter.strip().lstrip('@') if twitter else None  # Remove @ if included
    db_user.linkedin = linkedin.strip() if linkedin else None

    # Organisation details
    db_user.organisation_website = organisation_website.strip() if organisation_website else None
    db_user.organisation_notes = organisation_notes.strip() if organisation_notes else None

    # Strategy preference fields
    db_user.risk_level = risk_level if risk_level else None
    db_user.data_sensitivity = data_sensitivity if data_sensitivity else None
    db_user.budget = budget if budget else None
    db_user.deployment_pref = deployment_pref if deployment_pref else None
    db_user.use_cases = ','.join(use_cases) if use_cases else None

    db.commit()
    logger.info(f"Profile updated for user {db_user.email}: display_name={db_user.display_name}, role={db_user.role}")

    return RedirectResponse(url="/profile?success=1", status_code=303)


@router.get("/my-suggestions", response_class=HTMLResponse)
async def my_tool_suggestions(
    request: Request,
    user: User = Depends(require_auth_page),
    db: Session = Depends(get_db),
):
    """Show user their submitted tool suggestions."""
    from sqlalchemy import desc
    from app.models.tool_suggestion import ToolSuggestion

    suggestions = db.query(ToolSuggestion).filter(
        ToolSuggestion.submitted_by == user.id
    ).order_by(desc(ToolSuggestion.submitted_at)).all()

    return templates.TemplateResponse(
        "profile/my_suggestions.html",
        {
            "request": request,
            "user": user,
            "suggestions": suggestions,
        }
    )
