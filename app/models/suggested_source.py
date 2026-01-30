"""SuggestedSource model for user-submitted source suggestions."""
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text,
    ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db import Base


class SuggestedSource(Base):
    """User-suggested source for admin review.

    Users can suggest sources (articles, reports, studies) that may be
    valuable for the platform. Admins review and either approve (adding
    to the sources library) or reject them.
    """

    __tablename__ = "suggested_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Submitted by
    submitted_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source details
    title = Column(String(500), nullable=False)
    url = Column(String(2000), nullable=False)
    source_type = Column(String(50), nullable=False, default="article")  # article, report, study
    excerpt = Column(Text, nullable=True)  # User's description of the source
    why_valuable = Column(Text, nullable=True)  # Why this source is valuable

    # Review workflow
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status values: "pending", "approved", "rejected"
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)  # Admin notes on decision

    # If approved, track which batch it was added to
    added_to_batch = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    submitter = relationship("User", foreign_keys=[submitted_by], backref="suggested_sources")
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name='ck_suggested_source_status'
        ),
        CheckConstraint(
            "source_type IN ('article', 'report', 'study', 'guide', 'other')",
            name='ck_suggested_source_type'
        ),
    )
