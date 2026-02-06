"""Domain models for Knowledge Store.

This module exports core domain entities:
- Document: Document metadata
- DocumentVersion: Version history
- Chunk: Document chunks
- AclEntry: Access control
- AuditLog: Audit trail
- MilvusChunk: Vector chunk for Milvus
- SearchHit: Search result
"""

from src.domain.document import AclEntry, AuditLog, Chunk, Document, DocumentVersion
from src.domain.search import MilvusChunk, SearchHit

__all__ = [
    "Document",
    "DocumentVersion",
    "Chunk",
    "AclEntry",
    "AuditLog",
    "MilvusChunk",
    "SearchHit",
]
