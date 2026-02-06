"""ACL service for access control.

This module provides access control list (ACL) management:
- Permission hierarchy (admin > write > read)
- User/Group/Org principal types
- Milvus filter generation for search
- Access checking and management

Example:
    >>> from src.services.acl_service import get_acl_service
    >>> service = get_acl_service(repository)
    >>> doc_uuids = await service.get_accessible_documents("user1", ["group1"])
    >>> filter_expr = service.build_milvus_filter(doc_uuids)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    pass


class PrincipalType(str, Enum):
    """Type of principal for ACL.

    Attributes:
        USER: Individual user
        GROUP: User group
        ORG: Organization (use 'ALL' for public)
        ROLE: Role-based access
    """

    USER = "user"
    GROUP = "group"
    ORG = "org"
    ROLE = "role"


class Permission(str, Enum):
    """Permission level with hierarchy support.

    Hierarchy: ADMIN > DELETE > WRITE > READ
    """

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"

    def includes(self, other: Permission) -> bool:
        """Check if this permission includes another.

        Admin > Delete > Write > Read

        Args:
            other: Permission to check

        Returns:
            True if this permission includes the other
        """
        hierarchy = {
            Permission.READ: 0,
            Permission.WRITE: 1,
            Permission.DELETE: 2,
            Permission.ADMIN: 3,
        }
        return hierarchy[self] >= hierarchy[other]


@dataclass
class AclEntryData:
    """ACL entry data model for service layer.

    Attributes:
        doc_uuid: Document UUID
        principal_type: Type of principal
        principal_id: Principal identifier
        permission: Permission level
        id: Entry ID (optional)
        granted_by: User who granted permission
        expires_at: Expiration time
        created_at: Creation timestamp
    """

    doc_uuid: str
    principal_type: PrincipalType
    principal_id: str
    permission: Permission
    id: int | str | None = None
    granted_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class AclRepositoryProtocol(Protocol):
    """Protocol for ACL repository operations.

    Implementations should provide database access for ACL operations.
    """

    async def get_accessible_doc_uuids(
        self,
        user_id: str,
        user_groups: list[str],
    ) -> list[str]:
        """Get accessible document UUIDs for user.

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to

        Returns:
            List of accessible document UUIDs
        """
        ...

    async def check_document_access(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str],
        permission: Permission,
    ) -> bool:
        """Check if user has permission on document.

        Args:
            doc_uuid: Document UUID
            user_id: User identifier
            user_groups: List of group IDs
            permission: Required permission

        Returns:
            True if user has the required permission
        """
        ...

    async def create_acl_entry(self, entry: AclEntryData) -> AclEntryData:
        """Create ACL entry.

        Args:
            entry: ACL entry to create

        Returns:
            Created ACL entry with ID
        """
        ...

    async def delete_acl_entry(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
    ) -> bool:
        """Delete ACL entry.

        Args:
            doc_uuid: Document UUID
            principal_type: Type of principal
            principal_id: Principal identifier

        Returns:
            True if entry was deleted
        """
        ...

    async def get_document_acl(self, doc_uuid: str) -> list[AclEntryData]:
        """Get all ACL entries for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of ACL entries
        """
        ...


class AclService:
    """Service for ACL-based access control.

    Provides methods for:
    - Querying accessible documents
    - Building Milvus filter expressions
    - Checking specific document access
    - Managing ACL entries (grant/revoke)

    Example:
        >>> service = AclService(repository)
        >>> docs = await service.get_accessible_documents("user1", ["group1"])
        >>> has_access = await service.check_access("user1", ["group1"], "doc-uuid")
    """

    def __init__(self, repository: AclRepositoryProtocol) -> None:
        """Initialize ACL service.

        Args:
            repository: ACL repository implementation
        """
        self._repository = repository

    async def get_accessible_documents(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> list[str]:
        """Get list of accessible document UUIDs.

        Checks access based on:
        1. User principal matches user_id
        2. Group principal matches any of user_groups
        3. Org principal is 'ALL' (public)

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to

        Returns:
            List of accessible document UUIDs
        """
        groups = user_groups or []
        return await self._repository.get_accessible_doc_uuids(user_id, groups)

    def build_milvus_filter(self, doc_uuids: list[str]) -> str:
        """Build Milvus filter expression for accessible documents.

        Args:
            doc_uuids: List of accessible document UUIDs

        Returns:
            Milvus filter expression string

        Note:
            Returns expression matching nothing for empty list.
        """
        if not doc_uuids:
            return 'doc_uuid == "__NONE__"'

        escaped = [f'"{uuid}"' for uuid in doc_uuids]
        return f"doc_uuid in [{', '.join(escaped)}]"

    async def get_accessible_documents_filter(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> str:
        """Get Milvus filter expression for accessible documents.

        Convenience method combining get_accessible_documents and build_milvus_filter.

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to

        Returns:
            Milvus filter expression
        """
        doc_uuids = await self.get_accessible_documents(user_id, user_groups)
        return self.build_milvus_filter(doc_uuids)

    async def check_access(
        self,
        user_id: str,
        user_groups: list[str] | None,
        doc_uuid: str,
        permission: Permission = Permission.READ,
    ) -> bool:
        """Check if user has permission on specific document.

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to
            doc_uuid: Document UUID to check
            permission: Required permission level

        Returns:
            True if user has the required permission
        """
        groups = user_groups or []
        return await self._repository.check_document_access(
            doc_uuid=doc_uuid,
            user_id=user_id,
            user_groups=groups,
            permission=permission,
        )

    async def grant_access(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
        permission: Permission = Permission.READ,
        granted_by: str | None = None,
        expires_at: datetime | None = None,
    ) -> AclEntryData:
        """Grant access to a document.

        Args:
            doc_uuid: Document UUID
            principal_type: Type of principal (user, group, org, role)
            principal_id: Principal identifier
            permission: Permission to grant
            granted_by: User granting the permission
            expires_at: When permission expires

        Returns:
            Created ACL entry
        """
        entry = AclEntryData(
            doc_uuid=doc_uuid,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            granted_by=granted_by,
            expires_at=expires_at,
        )
        return await self._repository.create_acl_entry(entry)

    async def revoke_access(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
    ) -> bool:
        """Revoke access from a document.

        Args:
            doc_uuid: Document UUID
            principal_type: Type of principal
            principal_id: Principal identifier

        Returns:
            True if entry was deleted
        """
        return await self._repository.delete_acl_entry(
            doc_uuid=doc_uuid,
            principal_type=principal_type,
            principal_id=principal_id,
        )

    async def grant_public_access(
        self,
        doc_uuid: str,
        permission: Permission = Permission.READ,
        granted_by: str | None = None,
    ) -> AclEntryData:
        """Grant public (organization-wide) access.

        Creates an ACL entry with org='ALL' for public access.

        Args:
            doc_uuid: Document UUID
            permission: Permission to grant
            granted_by: User granting the permission

        Returns:
            Created ACL entry
        """
        return await self.grant_access(
            doc_uuid=doc_uuid,
            principal_type=PrincipalType.ORG,
            principal_id="ALL",
            permission=permission,
            granted_by=granted_by,
        )

    async def get_document_acl(self, doc_uuid: str) -> list[AclEntryData]:
        """Get all ACL entries for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of ACL entries for the document
        """
        return await self._repository.get_document_acl(doc_uuid)


# =============================================================================
# Singleton Factory
# =============================================================================

_service: AclService | None = None


def get_acl_service(repository: AclRepositoryProtocol | None = None) -> AclService:
    """Get or create ACL service singleton.

    Args:
        repository: Repository instance (required on first call)

    Returns:
        AclService instance

    Raises:
        ValueError: If repository not provided on first call
    """
    global _service
    if _service is None:
        if repository is None:
            raise ValueError("Repository required for first initialization")
        _service = AclService(repository)
    return _service


def close_acl_service() -> None:
    """Close the ACL service singleton."""
    global _service
    _service = None


def reset_acl_service() -> None:
    """Reset ACL service singleton (for testing)."""
    global _service
    _service = None
