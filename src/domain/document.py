"""Document domain models.

This module defines the core domain entities for document management:
- Document: Document metadata and ownership
- DocumentVersion: Version history tracking
- Chunk: Document chunks for vector/graph storage
- AclEntry: Access control list entry
- AuditLog: User action audit trail
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Document entity representing document metadata.

    Attributes:
        doc_uuid: Unique document identifier
        title: Document title
        source: Source system (wiki, agit, gdocs, slack, confluence, notion, file)
        source_url: Original document URL
        owner_id: Document owner user ID
        owner_org: Document owner organization
        status: Document status (draft, published, archived)
        security_level: Security classification
        current_version_id: Reference to current active version
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    doc_uuid: UUID | None = None
    title: str
    source: Literal["wiki", "agit", "gdocs", "slack", "confluence", "notion", "file"]
    source_url: str
    owner_id: str
    owner_org: str
    status: Literal["draft", "published", "archived"] = "draft"
    security_level: Literal["public", "internal", "confidential"] = "internal"
    current_version_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentVersion(BaseModel):
    """Document version entity for version history.

    Attributes:
        version_id: Unique version identifier
        doc_uuid: Parent document UUID
        version_no: Sequential version number
        content_hash: SHA-256 hash of content
        content_size: Content size in bytes
        effective_from: When version becomes effective
        effective_until: When version expires
        approved_by: Approver user ID
        approval_date: Approval timestamp
        change_summary: Summary of changes
        created_at: Creation timestamp
    """

    version_id: UUID | None = None
    doc_uuid: UUID
    version_no: int
    content_hash: str
    content_size: int | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None
    approved_by: str | None = None
    approval_date: datetime | None = None
    change_summary: str | None = None
    created_at: datetime | None = None


class Chunk(BaseModel):
    """Document chunk entity for vector/graph mapping.

    Attributes:
        chunk_uuid: Unique chunk identifier
        doc_uuid: Parent document UUID
        version_id: Parent version UUID
        chunk_no: Sequential chunk number
        section_path: Hierarchical section path
        chunk_text: Chunk text content
        char_start: Start character position
        char_end: End character position
        token_count: Number of tokens
        milvus_id: Vector ID in Milvus
        neo4j_node_id: Node ID in Neo4j
        embedding_model: Embedding model used
        created_at: Creation timestamp
    """

    chunk_uuid: UUID | None = None
    doc_uuid: UUID
    version_id: UUID
    chunk_no: int
    section_path: str | None = None
    chunk_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    token_count: int | None = None
    milvus_id: str | None = None
    neo4j_node_id: str | None = None
    embedding_model: str | None = None
    created_at: datetime | None = None


class AclEntry(BaseModel):
    """ACL entry entity for access control.

    Attributes:
        id: Unique entry identifier
        doc_uuid: Document UUID
        principal_type: Type of principal (user, group, org, role)
        principal_id: Principal identifier
        permission: Permission level (read, write, admin, delete)
        granted_by: User who granted permission
        expires_at: Permission expiration time
        created_at: Creation timestamp
    """

    id: UUID | None = None
    doc_uuid: UUID
    principal_type: Literal["user", "group", "org", "role"]
    principal_id: str
    permission: Literal["read", "write", "admin", "delete"]
    granted_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class AuditLog(BaseModel):
    """Audit log entity for tracking user actions.

    Attributes:
        log_id: Unique log identifier
        user_id: User who performed action
        user_org: User's organization
        action: Type of action
        resource_type: Type of resource affected
        doc_uuid: Document UUID (if applicable)
        query_text: Search query (if applicable)
        retrieved_docs: Retrieved document UUIDs (if applicable)
        result_count: Number of results returned
        response_time_ms: Response time in milliseconds
        ip_address: Client IP address
        user_agent: Client user agent
        metadata: Additional context
        timestamp: Action timestamp
    """

    log_id: UUID | None = None
    user_id: str
    user_org: str | None = None
    action: Literal[
        "search", "view", "create", "update", "delete", "export", "share", "permission_change"
    ]
    resource_type: Literal["document", "chunk", "acl", "system"] = "document"
    doc_uuid: UUID | None = None
    query_text: str | None = None
    retrieved_docs: list[UUID] | None = None
    result_count: int | None = None
    response_time_ms: int | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict | None = Field(default_factory=dict)
    timestamp: datetime | None = None
