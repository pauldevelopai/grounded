"""Authentication dependencies for route protection."""
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User
from app.auth.jwt import decode_token


async def get_current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """
    Get the current user from the access token cookie (optional, returns None if not authenticated).

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    token = request.cookies.get("access_token")
    if not token:
        return None

    payload = decode_token(token)
    if payload is None:
        return None

    if payload.get("type") != "access":
        return None

    user_id: str = payload.get("sub")
    if user_id is None:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Get the current user from the access token cookie (required).

    Args:
        request: FastAPI request object
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If not authenticated or token invalid
    """
    user = await get_current_user_optional(request, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    Require the current user to be an admin.

    Args:
        current_user: Current authenticated user

    Returns:
        User object if admin

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
