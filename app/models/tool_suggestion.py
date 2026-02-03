"""ToolSuggestion model for user-submitted tool suggestions."""
from sqlalchemy import (
    Column, String, DateTime, Text,
    ForeignKey, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db import Base


class ToolSuggestion(Base):
    """User-suggested tool for admin review.

    Users can suggest AI tools that may be valuable for the platform.
    Admins review and either approve (converting to DiscoveredTool) or reject them.
    """

    __tablename__ = "tool_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tool info from user
    name = Column(String(500), nullable=False)
    url = Column(String(2000), nullable=False)
    description = Column(Text, nullable=True)
    why_valuable = Column(Text, nullable=True)  # User's justification
    use_cases = Column(Text, nullable=True)  # What they'd use it for

    # Submitter
    submitted_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    submitted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Review workflow (matches SuggestedSource pattern)
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status values: "pending", "approved", "rejected", "converted"
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)  # Admin notes on decision

    # If approved and converted to DiscoveredTool
    converted_tool_id = Column(
        UUID(as_uuid=True),
        ForeignKey("discovered_tools.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    submitter = relationship("User", foreign_keys=[submitted_by], backref="tool_suggestions")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    converted_tool = relationship("DiscoveredTool", foreign_keys=[converted_tool_id])

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'converted')",
            name='ck_tool_suggestion_status'
        ),
    )
