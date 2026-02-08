"""Audit domain models.

This module provides audit logging models for tracking user actions:
- AuditAction: Types of auditable actions
- ResourceType: Types of resources being audited
- AuditLogEntry: Individual audit log entry
- AuditQuery: Query parameters for searching audit logs
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuditAction(str, Enum):
    """Audit action types.

    Categorizes all auditable actions in the system.
    """

    # Search actions
    SEARCH = "search"
    SEARCH_DENSE = "search_dense"
    SEARCH_SPARSE = "search_sparse"
    SEARCH_GRAPH = "search_graph"
    SEARCH_HYBRID = "search_hybrid"

    # Document actions
    DOCUMENT_CREATE = "document_create"
    DOCUMENT_READ = "document_read"
    DOCUMENT_UPDATE = "document_update"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_LIST = "document_list"

    # Permission actions
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"
    PERMISSION_CHECK = "permission_check"

    # Export actions
    EXPORT = "export"

    # Share actions
    SHARE = "share"


class ResourceType(str, Enum):
    """Resource types for audit logging.

    Identifies the type of resource being accessed or modified.
    """

    DOCUMENT = "document"
    CHUNK = "chunk"
    SEARCH = "search"
    PERMISSION = "permission"
    ACL = "acl"
    SYSTEM = "system"


@dataclass
class AuditLogEntry:
    """Audit log entry.

    Represents a single audit event with all relevant context.

    Attributes:
        user_id: User who performed the action
        action: Type of action performed
        resource_type: Type of resource affected
        resource_id: ID of the specific resource (e.g., doc_uuid)
        query_text: Search query text (for search actions)
        retrieved_docs: List of document UUIDs returned (for search actions)
        metadata: Additional context as key-value pairs
        ip_address: Client IP address
        user_agent: Client user agent string
        created_at: Timestamp when action occurred
        id: Database record ID (set after persistence)
    """

    user_id: str
    action: AuditAction
    resource_type: ResourceType
    resource_id: str | None = None
    query_text: str | None = None
    retrieved_docs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage.

        Returns:
            Dictionary representation suitable for database storage
        """
        return {
            "user_id": self.user_id,
            "action": self.action.value,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "query_text": self.query_text,
            "retrieved_docs": self.retrieved_docs,
            "metadata": self.metadata,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuditLogEntry:
        """Create instance from dictionary.

        Args:
            data: Dictionary with audit log data

        Returns:
            AuditLogEntry instance
        """
        # Parse timestamp if string
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.utcnow()

        return cls(
            user_id=data["user_id"],
            action=AuditAction(data["action"]),
            resource_type=ResourceType(data["resource_type"]),
            resource_id=data.get("resource_id"),
            query_text=data.get("query_text"),
            retrieved_docs=data.get("retrieved_docs", []),
            metadata=data.get("metadata", {}),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
            created_at=created_at,
            id=data.get("id"),
        )


@dataclass
class AuditQuery:
    """Query parameters for audit logs.

    Supports filtering and pagination of audit log queries.

    Attributes:
        user_id: Filter by user ID
        action: Filter by action type
        resource_type: Filter by resource type
        resource_id: Filter by specific resource ID
        start_time: Filter by minimum timestamp
        end_time: Filter by maximum timestamp
        limit: Maximum number of results
        offset: Number of results to skip
    """

    user_id: str | None = None
    action: AuditAction | None = None
    resource_type: ResourceType | None = None
    resource_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for query building.

        Returns:
            Dictionary with non-None query parameters
        """
        result: dict[str, Any] = {}

        if self.user_id is not None:
            result["user_id"] = self.user_id
        if self.action is not None:
            result["action"] = self.action.value
        if self.resource_type is not None:
            result["resource_type"] = self.resource_type.value
        if self.resource_id is not None:
            result["resource_id"] = self.resource_id
        if self.start_time is not None:
            result["start_time"] = self.start_time
        if self.end_time is not None:
            result["end_time"] = self.end_time

        result["limit"] = self.limit
        result["offset"] = self.offset

        return result
