"""Embeddings service with pluggable providers."""
import hashlib
from typing import List, Optional, Protocol
from openai import OpenAI
from sqlalchemy.orm import Session
from sqlalchemy import UUID

from app.settings import settings
from app.models.toolkit import ToolkitChunk


class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def create_embedding(self, text: str) -> List[float]:
        """Create embedding for text."""
        ...

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        ...


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider."""

    def __init__(self, api_key: str, model: str, dimensions: int):
        """Initialize OpenAI client."""
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self._dimensions = dimensions

    def create_embedding(self, text: str) -> List[float]:
        """Create embedding using OpenAI API."""
        kwargs = {"model": self.model, "input": text}
        # Only text-embedding-3-* models support the dimensions parameter
        if self.model.startswith("text-embedding-3"):
            kwargs["dimensions"] = self._dimensions
        response = self.client.embeddings.create(**kwargs)
        return response.data[0].embedding

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return self._dimensions


class LocalStubEmbeddingProvider:
    """
    Deterministic stub provider for tests.

    Creates fake embeddings based on text hash - same text always produces
    same embedding, no external API calls required.
    """

    def __init__(self, dimensions: int = 1536):
        """Initialize with specified dimensions."""
        self._dimensions = dimensions

    def create_embedding(self, text: str) -> List[float]:
        """
        Create deterministic embedding from text hash.

        Uses SHA256 hash of text to generate consistent embeddings.
        """
        # Hash the text
        hash_bytes = hashlib.sha256(text.encode()).digest()

        # Convert hash bytes to floats in range [-1, 1]
        embedding = []
        for i in range(self._dimensions):
            # Use hash bytes cyclically
            byte_idx = i % len(hash_bytes)
            # Convert byte (0-255) to float (-1 to 1)
            value = (hash_bytes[byte_idx] / 127.5) - 1.0
            embedding.append(value)

        # Normalize to unit length (typical for embeddings)
        magnitude = sum(x**2 for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]

        return embedding

    @property
    def dimensions(self) -> int:
        """Return embedding dimensions."""
        return self._dimensions


def get_embedding_provider() -> Optional[EmbeddingProvider]:
    """
    Get configured embedding provider.

    Returns:
        EmbeddingProvider instance or None if provider is not configured

    Raises:
        ValueError: If provider is 'openai' but API key is invalid
    """
    provider_type = settings.EMBEDDING_PROVIDER

    if provider_type == "openai":
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-your"):
            raise ValueError(
                "OpenAI provider selected but OPENAI_API_KEY is not configured. "
                "Set OPENAI_API_KEY or change EMBEDDING_PROVIDER to 'local_stub'."
            )
        return OpenAIEmbeddingProvider(
            api_key=settings.OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS
        )

    elif provider_type == "local_stub":
        return LocalStubEmbeddingProvider(dimensions=settings.EMBEDDING_DIMENSIONS)

    return None


def create_embedding(text: str, provider: Optional[EmbeddingProvider] = None) -> Optional[List[float]]:
    """
    Create embedding for a single text.

    Args:
        text: Text to embed
        provider: Optional provider instance (will get from settings if not provided)

    Returns:
        Embedding vector or None if provider not configured
    """
    if provider is None:
        provider = get_embedding_provider()

    if provider is None:
        return None

    return provider.create_embedding(text)


def create_embeddings_for_document(db: Session, document_id: UUID) -> int:
    """
    Create embeddings for all chunks in a document.

    Args:
        db: Database session
        document_id: Document ID

    Returns:
        Number of chunks with embeddings created
    """
    provider = get_embedding_provider()
    if provider is None:
        # No provider configured, skip embedding creation
        return 0

    # Get all chunks for this document that don't have embeddings
    chunks = db.query(ToolkitChunk).filter(
        ToolkitChunk.document_id == document_id,
        ToolkitChunk.embedding.is_(None)
    ).all()

    count = 0
    for chunk in chunks:
        try:
            embedding = provider.create_embedding(chunk.chunk_text)
            if embedding:
                chunk.embedding = embedding
                count += 1
        except Exception as e:
            print(f"Error creating embedding for chunk {chunk.id}: {e}")
            continue

    db.commit()
    return count
