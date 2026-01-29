"""Review models for tool ratings and reviews."""
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text,
    ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database import Base


class ToolReview(Base):
    """Tool review table."""

    __tablename__ = "tool_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    tool_slug = Column(String, nullable=False, index=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    use_case_tag = Column(String, nullable=True)
    is_hidden = Column(Boolean, default=False, nullable=False)
    hidden_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="reviews")
    votes = relationship("ReviewVote", back_populates="review", cascade="all, delete-orphan")
    flags = relationship("ReviewFlag", back_populates="review", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('user_id', 'tool_slug', name='uq_user_tool_review'),
        CheckConstraint('rating >= 1 AND rating <= 5', name='ck_rating_range'),
    )


class ReviewVote(Base):
    """Review vote table for helpful/not helpful votes."""

    __tablename__ = "review_votes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tool_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    is_helpful = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    review = relationship("ToolReview", back_populates="votes")
    user = relationship("User", backref="review_votes")

    __table_args__ = (
        UniqueConstraint('review_id', 'user_id', name='uq_review_user_vote'),
    )


class ReviewFlag(Base):
    """Review flag table for moderation."""

    __tablename__ = "review_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tool_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    reason = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolution_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    review = relationship("ToolReview", back_populates="flags")
    user = relationship("User", foreign_keys=[user_id], backref="review_flags")
    resolver = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        UniqueConstraint('review_id', 'user_id', name='uq_review_user_flag'),
    )
