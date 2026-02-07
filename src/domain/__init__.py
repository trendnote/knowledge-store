"""Domain models for Knowledge Store.

This module exports core domain entities:
- Document: Document metadata
- DocumentVersion: Version history
- Chunk: Document chunks
- AclEntry: Access control
- AuditLog: Audit trail
- MilvusChunk: Vector chunk for Milvus
- SearchHit: Search result
- DocumentNode: Graph document node
- ChunkNode: Graph chunk node
- Entity: Entity mentioned in chunks
- GraphSearchResult: Graph search result
"""

from src.domain.document import AclEntry, AuditLog, Chunk, Document, DocumentVersion
from src.domain.graph import ChunkNode, DocumentNode, Entity, GraphSearchResult
from src.domain.search import (
    MilvusChunk,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchType,
)

__all__ = [
    "Document",
    "DocumentVersion",
    "Chunk",
    "AclEntry",
    "AuditLog",
    "MilvusChunk",
    "SearchHit",
    "SearchRequest",
    "SearchResponse",
    "SearchType",
    "DocumentNode",
    "ChunkNode",
    "Entity",
    "GraphSearchResult",
]
