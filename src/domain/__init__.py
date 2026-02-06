"""Domain models for Knowledge Store.

This module exports core domain entities:
- Document: Document metadata
- DocumentVersion: Version history
- Chunk: Document chunks
- AclEntry: Access control
- AuditLog: Audit trail
"""

from src.domain.document import AclEntry, AuditLog, Chunk, Document, DocumentVersion

__all__ = [
    "Document",
    "DocumentVersion",
    "Chunk",
    "AclEntry",
    "AuditLog",
]
