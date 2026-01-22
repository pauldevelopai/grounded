"""Toolkit document and chunk models."""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
import uuid
from app.database import Base


class ToolkitDocument(Base):
    """Toolkit document versions."""

    __tablename__ = "toolkit_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_tag = Column(String, unique=True, nullable=False, index=True)
    source_filename = Column(String, nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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
    cluster = Column(String, nullable=True)
    section = Column(String, nullable=True)
    tool_name = Column(String, nullable=True)
    tags = Column(JSONB, nullable=True)
    embedding = Column(Vector(1536), nullable=True)  # OpenAI text-embedding-3-small dimension
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
