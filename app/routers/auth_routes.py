"""Authentication routes."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.auth import create_user, authenticate_user, create_session, delete_session
from app.settings import settings


router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request}
    )


@router.post("/auth/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process login form."""
    user = authenticate_user(db, username, password)

    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": {}, "error": "Invalid username or password"}
        )

    # Create session
    session = create_session(db, str(user.id))

    # Redirect to toolkit with session cookie
    response = RedirectResponse(url="/toolkit", status_code=303)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session.session_token,
        httponly=settings.COOKIE_HTTPONLY,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.SESSION_MAX_AGE
    )

    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request}
    )


@router.post("/auth/register")
async def register(
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process registration form."""
    # Validate password length
    if len(password) < 8:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": {}, "error": "Password must be at least 8 characters"}
        )

    try:
        # Create user
        user = create_user(db, email, username, password)

        # Create session
        session = create_session(db, str(user.id))

        # Redirect to toolkit with session cookie
        response = RedirectResponse(url="/toolkit", status_code=303)
        response.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=session.session_token,
            httponly=settings.COOKIE_HTTPONLY,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.SESSION_MAX_AGE
        )

        return response

    except ValueError as e:
        return templates.TemplateResponse(
            "auth/register.html",
            {"request": {}, "error": str(e)}
        )


@router.post("/auth/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """Logout (delete session)."""
    session_token = request.cookies.get("session")

    if session_token:
        delete_session(db, session_token)

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)

    return response
