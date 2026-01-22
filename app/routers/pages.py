"""HTML page routes."""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from app.auth.dependencies import get_current_user_optional
from app.models.user import User
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: User = Depends(get_current_user_optional)):
    """Login page."""
    # Redirect if already logged in
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, user: User = Depends(get_current_user_optional)):
    """Registration page."""
    # Redirect if already logged in
    if user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/logout")
async def logout_redirect():
    """Logout and redirect to home."""
    # The actual logout happens via API, this just redirects
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return response
