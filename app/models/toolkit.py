"""Toolkit document and chunk models."""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from app.db import Base


class ToolkitDocument(Base):
    """Toolkit document versions."""

    __tablename__ = "toolkit_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_tag = Column(String, unique=True, nullable=False, index=True)
    source_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)  # Path to uploaded file
    upload_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class ToolkitChunk(Base):
    """Toolkit content chunks with embeddings."""

    __tablename__ = "toolkit_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("toolkit_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    heading = Column(String, nullable=True)  # Parent heading
    chunk_metadata = Column(JSONB, nullable=True)  # Additional metadata
    embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small dimension
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChatLog(Base):
    """Chat log for Q&A with citations."""

    __tablename__ = "chat_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    citations = Column(JSONB, nullable=False)  # List of citation objects
    similarity_score = Column(JSONB, nullable=True)  # Top similarity scores
    filters_applied = Column(JSONB, nullable=True)  # Filters used in search
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class Feedback(Base):
    """User feedback on chat responses."""

    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_log_id = Column(UUID(as_uuid=True), ForeignKey("chat_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5
    issue_type = Column(String, nullable=True)  # hallucination, irrelevant, etc.
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class StrategyPlan(Base):
    """Strategy plan with grounded recommendations."""

    __tablename__ = "strategy_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Input parameters (wizard form)
    inputs = Column(JSONB, nullable=False)  # role, org_type, risk_level, etc.

    # Generated plan
    plan_text = Column(Text, nullable=False)  # The generated strategy plan

    # Citations from toolkit chunks
    citations = Column(JSONB, nullable=False)  # List of chunk citations used

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
