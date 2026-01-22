"""Browse toolkit content service."""
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.toolkit import ToolkitChunk, ToolkitDocument


class BrowseResult:
    """Browse result item."""

    def __init__(
        self,
        heading: str,
        excerpt: str,
        cluster: Optional[str] = None,
        tool_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        chunk_count: int = 1,
        first_chunk_id: Optional[str] = None
    ):
        self.heading = heading
        self.excerpt = excerpt
        self.cluster = cluster
        self.tool_name = tool_name
        self.tags = tags or []
        self.chunk_count = chunk_count
        self.first_chunk_id = first_chunk_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "heading": self.heading,
            "excerpt": self.excerpt,
            "cluster": self.cluster,
            "tool_name": self.tool_name,
            "tags": self.tags,
            "chunk_count": self.chunk_count,
            "first_chunk_id": self.first_chunk_id
        }


def get_available_clusters(db: Session) -> List[str]:
    """
    Get all unique cluster values from toolkit chunks metadata.

    Returns:
        List of cluster names sorted alphabetically
    """
    # Query all chunks with metadata
    chunks = db.query(ToolkitChunk).filter(
        ToolkitChunk.chunk_metadata.isnot(None)
    ).all()

    # Extract unique clusters
    clusters = set()
    for chunk in chunks:
        if chunk.chunk_metadata and 'cluster' in chunk.chunk_metadata:
            cluster = chunk.chunk_metadata['cluster']
            if cluster:
                clusters.add(cluster)

    return sorted(list(clusters))


def get_available_tags(db: Session) -> List[str]:
    """
    Get all unique tags from toolkit chunks metadata.

    Returns:
        List of tags sorted alphabetically
    """
    chunks = db.query(ToolkitChunk).filter(
        ToolkitChunk.chunk_metadata.isnot(None)
    ).all()

    tags = set()
    for chunk in chunks:
        if chunk.chunk_metadata and 'tags' in chunk.chunk_metadata:
            chunk_tags = chunk.chunk_metadata.get('tags', [])
            if isinstance(chunk_tags, list):
                tags.update(chunk_tags)

    return sorted(list(tags))


def browse_chunks(
    db: Session,
    cluster: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50
) -> List[BrowseResult]:
    """
    Browse toolkit content with optional filters.

    Groups results by heading (section) and shows excerpt from first chunk.

    Args:
        db: Database session
        cluster: Filter by cluster (from metadata)
        keyword: Search in chunk text and heading
        limit: Maximum results to return

    Returns:
        List of BrowseResult objects grouped by heading
    """
    # Start with base query
    query = (
        db.query(ToolkitChunk)
        .join(ToolkitDocument, ToolkitChunk.document_id == ToolkitDocument.id)
        .filter(ToolkitDocument.is_active == True)
    )

    # Apply cluster filter
    if cluster:
        query = query.filter(
            ToolkitChunk.chunk_metadata['cluster'].astext == cluster
        )

    # Apply keyword search
    if keyword:
        search_pattern = f"%{keyword}%"
        query = query.filter(
            or_(
                ToolkitChunk.chunk_text.ilike(search_pattern),
                ToolkitChunk.heading.ilike(search_pattern)
            )
        )

    # Get chunks ordered by heading
    chunks = query.order_by(
        ToolkitChunk.heading,
        ToolkitChunk.chunk_index
    ).all()

    # Group by heading
    grouped = {}
    for chunk in chunks:
        heading = chunk.heading or "Untitled Section"

        if heading not in grouped:
            # First chunk for this heading
            excerpt = chunk.chunk_text[:200]
            if len(chunk.chunk_text) > 200:
                excerpt += "..."

            # Extract metadata
            cluster_val = None
            tool_name = None
            tags = []

            if chunk.chunk_metadata:
                cluster_val = chunk.chunk_metadata.get('cluster')
                tool_name = chunk.chunk_metadata.get('tool_name')
                tags = chunk.chunk_metadata.get('tags', [])

            grouped[heading] = BrowseResult(
                heading=heading,
                excerpt=excerpt,
                cluster=cluster_val,
                tool_name=tool_name,
                tags=tags if isinstance(tags, list) else [],
                chunk_count=1,
                first_chunk_id=str(chunk.id)
            )
        else:
            # Increment chunk count for this heading
            grouped[heading].chunk_count += 1

    # Convert to list and limit
    results = list(grouped.values())
    return results[:limit]


def get_section_detail(
    db: Session,
    heading: str
) -> Optional[Dict[str, Any]]:
    """
    Get all chunks for a specific heading/section.

    Args:
        db: Database session
        heading: Section heading to fetch

    Returns:
        Dictionary with section info and all chunks, or None if not found
    """
    # Get all chunks with this heading
    chunks = (
        db.query(ToolkitChunk)
        .join(ToolkitDocument, ToolkitChunk.document_id == ToolkitDocument.id)
        .filter(ToolkitDocument.is_active == True)
        .filter(ToolkitChunk.heading == heading)
        .order_by(ToolkitChunk.chunk_index)
        .all()
    )

    if not chunks:
        return None

    # Combine all chunk text
    full_text = "\n\n".join([chunk.chunk_text for chunk in chunks])

    # Get metadata from first chunk
    first_chunk = chunks[0]
    cluster = None
    tool_name = None
    tags = []

    if first_chunk.chunk_metadata:
        cluster = first_chunk.chunk_metadata.get('cluster')
        tool_name = first_chunk.chunk_metadata.get('tool_name')
        tags = first_chunk.chunk_metadata.get('tags', [])

    return {
        "heading": heading,
        "full_text": full_text,
        "cluster": cluster,
        "tool_name": tool_name,
        "tags": tags if isinstance(tags, list) else [],
        "chunk_count": len(chunks),
        "chunks": [
            {
                "id": str(chunk.id),
                "text": chunk.chunk_text,
                "index": chunk.chunk_index
            }
            for chunk in chunks
        ]
    }


def search_chunks_by_text(
    db: Session,
    query_text: str,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Simple text search in chunks (for fallback when no embeddings).

    Args:
        db: Database session
        query_text: Text to search for
        limit: Maximum results

    Returns:
        List of matching chunks with metadata
    """
    search_pattern = f"%{query_text}%"

    chunks = (
        db.query(ToolkitChunk)
        .join(ToolkitDocument, ToolkitChunk.document_id == ToolkitDocument.id)
        .filter(ToolkitDocument.is_active == True)
        .filter(
            or_(
                ToolkitChunk.chunk_text.ilike(search_pattern),
                ToolkitChunk.heading.ilike(search_pattern)
            )
        )
        .limit(limit)
        .all()
    )

    results = []
    for chunk in chunks:
        excerpt = chunk.chunk_text[:200]
        if len(chunk.chunk_text) > 200:
            excerpt += "..."

        results.append({
            "id": str(chunk.id),
            "heading": chunk.heading or "Untitled",
            "excerpt": excerpt,
            "full_text": chunk.chunk_text,
            "cluster": chunk.chunk_metadata.get('cluster') if chunk.chunk_metadata else None,
            "tool_name": chunk.chunk_metadata.get('tool_name') if chunk.chunk_metadata else None,
            "tags": chunk.chunk_metadata.get('tags', []) if chunk.chunk_metadata else []
        })

    return results
