"""User feedback routes."""
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_auth
from app.models.auth import User
from app.models.toolkit import AppFeedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("/submit")
async def submit_feedback(
    request: Request,
    category: str = Form(...),
    message: str = Form(...),
    page_url: str = Form(None),
    user: User = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Submit app feedback from logged-in users.

    Returns JSON response for AJAX submission.
    """
    # Validate category
    valid_categories = ["bug", "feature", "question", "other"]
    if category not in valid_categories:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid category"}
        )

    # Validate message length
    if not message or len(message.strip()) < 10:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message must be at least 10 characters"}
        )

    if len(message) > 2000:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Message must be under 2000 characters"}
        )

    # Create feedback
    feedback = AppFeedback(
        user_id=user.id,
        category=category,
        message=message.strip(),
        page_url=page_url
    )

    db.add(feedback)
    db.commit()

    return JSONResponse(
        status_code=200,
        content={"success": True, "message": "Thank you for your feedback!"}
    )
