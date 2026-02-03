"""UserLearningProfile model for personalized AI suggestions."""
from sqlalchemy import (
    Column, String, DateTime, Text, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db import Base


class UserLearningProfile(Base):
    """User learning profile for personalized recommendations.

    Tracks accumulated user preferences learned from activity patterns.
    The AI uses this profile to generate personalized strategy recommendations.
    """

    __tablename__ = "user_learning_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # One profile per user
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Accumulated preferences (learned from activity)
    # Format: {cluster_slug: score} where score is 0.0-1.0
    preferred_clusters = Column(JSONB, nullable=True, default=dict)

    # Tool interaction tracking
    # Format: {tool_slug: {viewed: N, time_spent: M, dismissed: bool, favorited: bool}}
    tool_interests = Column(JSONB, nullable=True, default=dict)

    # Search history for context
    # Format: [{query: str, timestamp: str, results_clicked: [slug]}]
    searched_topics = Column(JSONB, nullable=True, default=list)

    # Feedback signals
    # Format: [{strategy_id: str, helpful: bool, implemented: [tool_slugs]}]
    strategy_feedback = Column(JSONB, nullable=True, default=list)

    # Explicitly dismissed tool recommendations
    # Format: [tool_slugs]
    dismissed_tools = Column(JSONB, nullable=True, default=list)

    # Favorited/bookmarked tools
    # Format: [tool_slugs]
    favorited_tools = Column(JSONB, nullable=True, default=list)

    # AI-generated profile summary (regenerated periodically)
    # This is a narrative summary the LLM uses for context
    profile_summary = Column(Text, nullable=True)
    last_summary_at = Column(DateTime(timezone=True), nullable=True)

    # Track how much activity has been processed
    last_activity_count = Column(JSONB, nullable=True, default=dict)
    # Format: {activity_type: count_processed}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="learning_profile", uselist=False)
