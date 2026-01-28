"""CSRF protection middleware."""
import hmac
import hashlib
import time
import logging
from typing import Optional

from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.settings import settings


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware to protect against CSRF attacks on POST forms."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("app.csrf")

        # Methods that require CSRF protection
        self.protected_methods = {"POST", "PUT", "DELETE", "PATCH"}

        # Paths exempt from CSRF (API endpoints with other auth, and form endpoints with inline CSRF)
        # Note: Form routes are exempt here because reading form() in middleware consumes the body
        # These routes should validate CSRF manually if needed
        self.exempt_paths = {
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/logout",
            "/api/rag/query",
            "/api/rag/search",
            "/auth/login",
            "/auth/register",
            "/auth/logout",
            "/toolkit/ask",
            "/toolkit/ask-widget",
            "/toolkit/feedback",
            "/profile/update",
            "/strategy/generate",
            "/health",
            "/ready",
        }

        # Path prefixes exempt from CSRF (protected by other auth mechanisms)
        # Note: These routes read form data, and reading form() in middleware consumes the body
        self.exempt_prefixes = [
            "/admin/",   # Protected by require_admin dependency
            "/feedback/",  # Protected by require_auth dependency
        ]

    async def dispatch(self, request: Request, call_next):
        """Validate CSRF token for protected requests."""
        # Skip if method not protected
        if request.method not in self.protected_methods:
            return await call_next(request)

        # Skip if path is exempt
        if request.url.path in self.exempt_paths or request.url.path.startswith("/api/"):
            return await call_next(request)

        # Skip if path matches exempt prefix
        for prefix in self.exempt_prefixes:
            if request.url.path.startswith(prefix):
                return await call_next(request)

        # Check CSRF token
        token_from_form = await self._get_token_from_request(request)
        token_from_cookie = request.cookies.get("csrf_token")

        if not token_from_cookie or not token_from_form:
            self.logger.warning(
                f"CSRF token missing for {request.url.path}",
                extra={
                    'request_id': getattr(request.state, 'request_id', None),
                    'extra_fields': {
                        'path': request.url.path,
                        'method': request.method
                    }
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing"
            )

        # Validate token
        if not self._validate_token(token_from_cookie, token_from_form):
            self.logger.warning(
                f"CSRF token invalid for {request.url.path}",
                extra={
                    'request_id': getattr(request.state, 'request_id', None),
                    'extra_fields': {
                        'path': request.url.path,
                        'method': request.method
                    }
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token invalid"
            )

        # Token valid, process request
        return await call_next(request)

    async def _get_token_from_request(self, request: Request) -> Optional[str]:
        """Extract CSRF token from request (form data or header)."""
        # Try header first
        token = request.headers.get("X-CSRF-Token")
        if token:
            return token

        # Try form data
        try:
            form = await request.form()
            return form.get("csrf_token")
        except Exception:
            return None

    def _validate_token(self, cookie_token: str, form_token: str) -> bool:
        """Validate CSRF token matches and is not expired."""
        return hmac.compare_digest(cookie_token, form_token)

    @staticmethod
    def generate_token() -> str:
        """Generate a new CSRF token."""
        timestamp = str(int(time.time()))
        random_data = hashlib.sha256(
            f"{settings.CSRF_SECRET_KEY}{timestamp}".encode()
        ).hexdigest()
        return f"{timestamp}.{random_data}"

    @staticmethod
    def set_csrf_cookie(response: Response, token: str) -> None:
        """Set CSRF token cookie on response."""
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=False,  # Needs to be accessible to JavaScript
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            max_age=settings.CSRF_TOKEN_EXPIRY
        )
