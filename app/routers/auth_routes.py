"""Authentication routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.auth import User
from app.dependencies import get_current_user
from app.services.auth import create_user, authenticate_user, create_session, delete_session
from app.settings import settings
from app.middleware.csrf import CSRFProtectionMiddleware
from app.templates_engine import templates
from app.products.registry import ProductRegistry, EditionRegistry


router = APIRouter(tags=["auth"])


def get_available_products():
    """Get all available products with their editions for login page."""
    all_products = ProductRegistry.list_all()
    products_with_editions = []

    for p in all_products:
        editions = EditionRegistry.list_for_product(p.id)
        # Only include products that have at least one edition
        if editions:
            products_with_editions.append({
                "product": p,
                "editions": editions,
            })

    return products_with_editions


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    response: Response,
    next: Optional[str] = None,
    user: Optional[User] = Depends(get_current_user),
):
    """Login page."""
    # Already logged in — redirect
    if user:
        return RedirectResponse(url=next or "/", status_code=302)

    csrf_token = CSRFProtectionMiddleware.generate_token()
    available_products = get_available_products()

    template_response = templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "user": None,
            "next": next or "",
            "available_products": available_products,
            "selected_product": "grounded",  # Default selection
        }
    )
    CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
    return template_response


@router.post("/auth/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    product: Optional[str] = Form(None),
    next: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """Process login form."""
    user = authenticate_user(db, username, password)

    available_products = get_available_products()

    if not user:
        csrf_token = CSRFProtectionMiddleware.generate_token()
        template_response = templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Invalid username or password",
                "csrf_token": csrf_token,
                "user": None,
                "next": next or "",
                "available_products": available_products,
                "selected_product": product or "grounded",
            }
        )
        CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
        return template_response

    # Get the form data to extract edition selection
    form_data = await request.form()
    edition_key = f"edition_{product}" if product else "edition_grounded"
    edition = form_data.get(edition_key)

    # Update user's product/edition preference
    if product:
        user.selected_product = product
        user.selected_edition = edition
        db.commit()

    # Validate redirect URL (must be relative, not protocol-relative)
    redirect_url = "/"
    if next and next.startswith("/") and not next.startswith("//"):
        redirect_url = next

    session = create_session(db, str(user.id))
    response = RedirectResponse(url=redirect_url, status_code=303)
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
async def register_page(
    request: Request,
    response: Response,
    user: Optional[User] = Depends(get_current_user),
):
    """Registration page."""
    if user:
        return RedirectResponse(url="/", status_code=302)

    csrf_token = CSRFProtectionMiddleware.generate_token()
    template_response = templates.TemplateResponse(
        "auth/register.html",
        {"request": request, "csrf_token": csrf_token, "user": None}
    )
    CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
    return template_response


@router.post("/auth/register")
async def register(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Process registration form."""
    if len(password) < 8:
        csrf_token = CSRFProtectionMiddleware.generate_token()
        template_response = templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": "Password must be at least 8 characters", "csrf_token": csrf_token, "user": None}
        )
        CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
        return template_response

    try:
        user = create_user(db, email, username, password)
        session = create_session(db, str(user.id))
        response = RedirectResponse(url="/", status_code=303)
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
        csrf_token = CSRFProtectionMiddleware.generate_token()
        template_response = templates.TemplateResponse(
            "auth/register.html",
            {"request": request, "error": str(e), "csrf_token": csrf_token, "user": None}
        )
        CSRFProtectionMiddleware.set_csrf_cookie(template_response, csrf_token)
        return template_response


@router.post("/auth/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """Logout (delete session)."""
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if session_token:
        delete_session(db, session_token)

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response
