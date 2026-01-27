"""Authentication service."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from sqlalchemy.orm import Session

from app.models.auth import User, Session as SessionModel


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(
        password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def create_user(
    db: Session,
    email: str,
    username: str,
    password: str,
    is_admin: bool = False
) -> User:
    """
    Create a new user account.

    Args:
        db: Database session
        email: User email (must be unique)
        username: Username (must be unique)
        password: Plain text password (will be hashed)
        is_admin: Whether user is an admin

    Returns:
        Created User object

    Raises:
        ValueError: If email or username already exists
    """
    # Check if email exists
    existing_email = db.query(User).filter(User.email == email).first()
    if existing_email:
        raise ValueError("Email already registered")

    # Check if username exists
    existing_username = db.query(User).filter(User.username == username).first()
    if existing_username:
        raise ValueError("Username already taken")

    # Create user
    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(password),
        is_admin=is_admin,
        is_active=True
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    Authenticate a user by username and password.

    Args:
        db: Database session
        username: Username or email
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    # Try to find user by username or email
    user = db.query(User).filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user:
        return None

    if not user.is_active:
        return None

    if not verify_password(password, user.hashed_password):
        return None

    return user


def create_session(db: Session, user_id: str, expires_in_days: int = 30) -> SessionModel:
    """
    Create a new session for a user.

    Args:
        db: Database session
        user_id: User ID
        expires_in_days: Number of days until session expires

    Returns:
        Created Session object
    """
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    session = SessionModel(
        user_id=user_id,
        session_token=session_token,
        expires_at=expires_at
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    return session


def get_session(db: Session, session_token: str) -> Optional[SessionModel]:
    """
    Get a session by token.

    Args:
        db: Database session
        session_token: Session token from cookie

    Returns:
        Session object if valid and not expired, None otherwise
    """
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token
    ).first()

    if not session:
        return None

    # Check if expired (use timezone-aware datetime)
    now = datetime.now(timezone.utc)
    if session.expires_at < now:
        db.delete(session)
        db.commit()
        return None

    return session


def get_user_from_session(db: Session, session_token: str) -> Optional[User]:
    """
    Get user from session token.

    Args:
        db: Database session
        session_token: Session token from cookie

    Returns:
        User object if session valid, None otherwise
    """
    session = get_session(db, session_token)
    if not session:
        return None

    user = db.query(User).filter(User.id == session.user_id).first()

    if not user or not user.is_active:
        return None

    return user


def delete_session(db: Session, session_token: str) -> None:
    """
    Delete a session (logout).

    Args:
        db: Database session
        session_token: Session token to delete
    """
    session = db.query(SessionModel).filter(
        SessionModel.session_token == session_token
    ).first()

    if session:
        db.delete(session)
        db.commit()
