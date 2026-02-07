"""Services module.

This module provides business logic services:
- AclService: Access control list management
- SearchService: Vector and graph search operations
- DocumentService: Document CRUD operations
"""

from src.services.acl_service import (
    AclEntryData,
    AclRepositoryProtocol,
    AclService,
    Permission,
    PrincipalType,
    close_acl_service,
    get_acl_service,
    reset_acl_service,
)
from src.services.document_service import (
    ChunkData,
    DocumentCreateRequest,
    DocumentResponse,
    DocumentService,
    DocumentUpdateRequest,
    get_document_service,
    reset_document_service,
    set_document_service,
)
from src.services.search_service import (
    SearchService,
    close_search_service,
    get_search_service,
    reset_search_service,
)

__all__ = [
    # ACL Service
    "AclEntryData",
    "AclRepositoryProtocol",
    "AclService",
    "Permission",
    "PrincipalType",
    "close_acl_service",
    "get_acl_service",
    "reset_acl_service",
    # Document Service
    "ChunkData",
    "DocumentCreateRequest",
    "DocumentResponse",
    "DocumentService",
    "DocumentUpdateRequest",
    "get_document_service",
    "reset_document_service",
    "set_document_service",
    # Search Service
    "SearchService",
    "close_search_service",
    "get_search_service",
    "reset_search_service",
]
