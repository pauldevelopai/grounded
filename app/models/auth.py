"""User authentication models."""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db import Base


class User(Base):
    """User account."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Profile fields
    display_name = Column(String, nullable=True)
    organisation = Column(String, nullable=True)
    organisation_type = Column(String, nullable=True)  # newsroom, freelance, ngo, academic, other
    role = Column(String, nullable=True)
    country = Column(String, nullable=True)
    interests = Column(Text, nullable=True)
    ai_experience_level = Column(String, nullable=True)  # beginner, intermediate, advanced

    # Strategy preferences (saved from strategy wizard)
    risk_level = Column(String, nullable=True)  # low, medium, high
    data_sensitivity = Column(String, nullable=True)  # public, internal, pii, regulated
    budget = Column(String, nullable=True)  # minimal, small, medium, large
    deployment_pref = Column(String, nullable=True)  # cloud, hybrid, sovereign
    use_cases = Column(Text, nullable=True)  # comma-separated list

    # Additional info
    bio = Column(Text, nullable=True)  # User bio/notes
    website = Column(String, nullable=True)
    twitter = Column(String, nullable=True)  # Twitter/X handle
    linkedin = Column(String, nullable=True)  # LinkedIn URL
    organisation_website = Column(String, nullable=True)
    organisation_notes = Column(Text, nullable=True)

    # Product/Edition preference
    selected_product = Column(String, nullable=True, default="grounded")
    selected_edition = Column(String, nullable=True)  # None means use active edition


class Session(Base):
    """User session for cookie-based auth."""

    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
