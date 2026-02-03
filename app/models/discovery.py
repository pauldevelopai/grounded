"""Discovery models for automated tool discovery pipeline."""
from sqlalchemy import (
    Column, String, Boolean, DateTime, Integer, Text, Float,
    ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.db import Base


class DiscoveredTool(Base):
    """Discovered tool from automated discovery pipeline."""

    __tablename__ = "discovered_tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic tool info
    name = Column(String, nullable=False, index=True)
    slug = Column(String, nullable=False, unique=True, index=True)
    url = Column(String, nullable=False, index=True)
    url_domain = Column(String, nullable=False, index=True)  # Extracted domain for dedup
    docs_url = Column(String, nullable=True)
    pricing_url = Column(String, nullable=True)

    # Description and content
    description = Column(Text, nullable=True)
    raw_description = Column(Text, nullable=True)  # Original scraped text
    ai_summary = Column(Text, nullable=True)  # AI-generated summary
    purpose = Column(Text, nullable=True)  # What the tool does / journalism relevance
    github_url = Column(String, nullable=True)  # GitHub repo URL if applicable

    # Categorization
    categories = Column(JSONB, nullable=True, default=list)  # List of categories/use cases
    tags = Column(JSONB, nullable=True, default=list)  # Auto-extracted tags

    # Discovery metadata
    source_type = Column(String, nullable=False, index=True)  # "github", "producthunt", "awesome_list", "directory"
    source_url = Column(String, nullable=False)  # Where we found it (required for attribution)
    source_name = Column(String, nullable=False)  # "GitHub Trending", "Product Hunt", "awesome-ai-tools"
    discovered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)  # Updated each time we re-discover
    last_updated_signal = Column(String, nullable=True)  # e.g., "2024-01-15" from GitHub

    # Source-specific metadata
    extra_data = Column(JSONB, nullable=True, default=dict)  # GitHub stars, PH votes, etc.

    # Quality assessment fields
    has_documentation = Column(Boolean, nullable=True)  # Does tool have docs?
    github_stars = Column(Integer, nullable=True)  # GitHub stars if applicable
    journalism_relevance_score = Column(Float, nullable=True)  # 0.0-1.0 journalism relevance
    quality_flags = Column(JSONB, nullable=True, default=dict)  # Quality issues/flags

    # CDI scores (set on approval)
    cdi_cost = Column(Integer, nullable=True)  # 0-10 cost score
    cdi_difficulty = Column(Integer, nullable=True)  # 0-10 difficulty score
    cdi_invasiveness = Column(Integer, nullable=True)  # 0-10 invasiveness score

    # Review workflow
    status = Column(String, nullable=False, default="pending_review", index=True)  # "pending_review", "approved", "rejected", "archived"
    confidence_score = Column(Float, nullable=False, default=0.5)  # 0.0-1.0, low confidence = needs review
    review_notes = Column(Text, nullable=True)
    reviewed_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    matches = relationship("ToolMatch", back_populates="tool", foreign_keys="ToolMatch.tool_id", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'archived')",
            name='ck_discovered_tool_status'
        ),
        CheckConstraint(
            "source_type IN ('github', 'producthunt', 'awesome_list', 'directory')",
            name='ck_discovered_tool_source_type'
        ),
        CheckConstraint(
            'confidence_score >= 0.0 AND confidence_score <= 1.0',
            name='ck_confidence_score_range'
        ),
    )


class DiscoveryRun(Base):
    """Tracks each discovery pipeline execution."""

    __tablename__ = "discovery_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="running", index=True)  # "running", "completed", "failed"
    source_type = Column(String, nullable=True)  # If running single source

    # Stats
    tools_found = Column(Integer, nullable=False, default=0)
    tools_new = Column(Integer, nullable=False, default=0)
    tools_updated = Column(Integer, nullable=False, default=0)
    tools_skipped = Column(Integer, nullable=False, default=0)  # Duplicates

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Configuration used for this run
    run_config = Column(JSONB, nullable=True, default=dict)

    # Who triggered it
    triggered_by = Column(String, nullable=True)  # "cron", "manual", user ID

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'cancelled')",
            name='ck_discovery_run_status'
        ),
    )


class ToolMatch(Base):
    """Tracks potential duplicates for review."""

    __tablename__ = "tool_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # The discovered tool
    tool_id = Column(
        UUID(as_uuid=True),
        ForeignKey("discovered_tools.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # What it matched against
    matched_tool_id = Column(
        UUID(as_uuid=True),
        ForeignKey("discovered_tools.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )  # If matched another discovered tool
    matched_kit_slug = Column(String, nullable=True, index=True)  # If matched a curated tool

    # Match details
    match_type = Column(String, nullable=False)  # "exact_url", "domain", "name_fuzzy", "description_similar"
    match_score = Column(Float, nullable=False)  # Confidence 0.0-1.0
    match_details = Column(JSONB, nullable=True)  # Additional context about the match

    # Resolution
    is_duplicate = Column(Boolean, nullable=True, default=None)  # None = unresolved, True/False = admin decision
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    tool = relationship("DiscoveredTool", back_populates="matches", foreign_keys=[tool_id])
    matched_tool = relationship("DiscoveredTool", foreign_keys=[matched_tool_id])
    resolver = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        CheckConstraint(
            "match_type IN ('exact_url', 'domain', 'name_fuzzy', 'name_exact', 'description_similar')",
            name='ck_tool_match_type'
        ),
        CheckConstraint(
            'match_score >= 0.0 AND match_score <= 1.0',
            name='ck_match_score_range'
        ),
        # Ensure at least one match target is specified
        CheckConstraint(
            'matched_tool_id IS NOT NULL OR matched_kit_slug IS NOT NULL',
            name='ck_match_target_required'
        ),
    )
