"""Document API router.

This module provides the Document API endpoints:
- POST /documents: Create a new document
- GET /documents: List accessible documents
- GET /documents/{doc_uuid}: Get a document by UUID
- PUT /documents/{doc_uuid}: Update a document
- DELETE /documents/{doc_uuid}: Delete a document

Authentication is handled via X-User-Id and X-User-Groups headers.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.api.schemas.documents import (
    DocumentCreateSchema,
    DocumentListResponseSchema,
    DocumentResponseSchema,
    DocumentStatusEnum,
    DocumentUpdateSchema,
    SecurityLevelEnum,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# =============================================================================
# Dependency Injection
# =============================================================================


async def get_document_service() -> Any:
    """Get document service instance.

    This is a placeholder that will be overridden during app initialization.

    Raises:
        NotImplementedError: Always, until properly configured
    """
    raise NotImplementedError("Document service not configured")


# =============================================================================
# Type Conversion Helpers
# =============================================================================


def _convert_status_to_domain(
    status_enum: DocumentStatusEnum | None,
) -> str | None:
    """Convert API status enum to domain string.

    Args:
        status_enum: API status enum

    Returns:
        Domain status string or None
    """
    if status_enum is None:
        return None
    return status_enum.value


def _convert_status_to_api(status_str: str) -> DocumentStatusEnum:
    """Convert domain status string to API enum.

    Args:
        status_str: Domain status string

    Returns:
        API status enum
    """
    return DocumentStatusEnum(status_str)


def _convert_security_to_api(security_str: str) -> SecurityLevelEnum:
    """Convert domain security string to API enum.

    Args:
        security_str: Domain security string

    Returns:
        API security level enum
    """
    return SecurityLevelEnum(security_str)


def _parse_user_groups(groups_header: str | None) -> list[str]:
    """Parse comma-separated user groups header.

    Args:
        groups_header: Comma-separated groups string

    Returns:
        List of group names
    """
    if not groups_header:
        return []
    return [g.strip() for g in groups_header.split(",") if g.strip()]


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "",
    response_model=DocumentResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Document",
    description="""
Create a new document with automatic chunking and embedding.

The document content will be:
1. Split into chunks based on chunk_size and chunk_overlap settings
2. Embedded using BGE-M3 (dense and sparse vectors)
3. Stored in PostgreSQL (metadata), Milvus (vectors), and Neo4j (graph)

**Authentication:**
- X-User-Id header is required
- X-User-Org header is optional (defaults to 'default')
""",
    responses={
        201: {
            "description": "Document created successfully",
            "model": DocumentResponseSchema,
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "example": {"detail": "Content cannot be empty"}
                }
            },
        },
        422: {
            "description": "Validation error",
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Failed to create document"}
                }
            },
        },
    },
)
async def create_document(
    request: DocumentCreateSchema,
    x_user_id: str = Header(description="User ID"),
    x_user_org: str = Header(description="User organization", default="default"),
    service: Any = Depends(get_document_service),
) -> DocumentResponseSchema:
    """Create a new document.

    Args:
        request: Document creation request
        service: Document service (injected)
        x_user_id: User ID from header
        x_user_org: User organization from header

    Returns:
        Created document response

    Raises:
        HTTPException: 400 for invalid request, 500 for internal errors
    """
    logger.info(f"Create document request: '{request.title}' by {x_user_id}")

    try:
        from src.services.document_service import DocumentCreateRequest

        domain_request = DocumentCreateRequest(
            title=request.title,
            content=request.content,
            owner_id=x_user_id,
            owner_org=x_user_org,
            source=request.source.value,
            source_url=request.source_url,
            security_level=request.security_level.value,
            metadata=request.metadata,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        response = await service.create_document(domain_request)

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            owner_org=response.owner_org,
            source=response.source,
            source_url=response.source_url,
            status=_convert_status_to_api(response.status),
            security_level=_convert_security_to_api(response.security_level),
            chunk_count=response.chunk_count,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except ValueError as e:
        logger.warning(f"Invalid create request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Create document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document",
        )


@router.get(
    "",
    response_model=DocumentListResponseSchema,
    summary="List Documents",
    description="""
List accessible documents with pagination and filtering.

Only documents the user has read access to will be returned.
Documents are ordered by creation date (newest first).

**Authentication:**
- X-User-Id header is required
- X-User-Groups header is optional (comma-separated group names)
""",
    responses={
        200: {
            "description": "List of documents",
            "model": DocumentListResponseSchema,
        },
    },
)
async def list_documents(
    x_user_id: str = Header(description="User ID"),
    x_user_groups: str | None = Header(description="Comma-separated group names", default=None),
    status_filter: DocumentStatusEnum | None = Query(alias="status", description="Filter by status", default=None),
    limit: int = Query(ge=1, le=100, description="Maximum documents per page", default=20),
    offset: int = Query(ge=0, description="Pagination offset", default=0),
    service: Any = Depends(get_document_service),
) -> DocumentListResponseSchema:
    """List accessible documents.

    Args:
        service: Document service (injected)
        x_user_id: User ID from header
        x_user_groups: Comma-separated group names from header
        status_filter: Optional status filter
        limit: Maximum documents per page
        offset: Pagination offset

    Returns:
        Paginated list of documents
    """
    logger.debug(f"List documents for user: {x_user_id}")

    groups = _parse_user_groups(x_user_groups)
    status_value = _convert_status_to_domain(status_filter)

    docs = await service.list_documents(
        user_id=x_user_id,
        user_groups=groups if groups else None,
        status=status_value,
        limit=limit,
        offset=offset,
    )

    return DocumentListResponseSchema(
        documents=[
            DocumentResponseSchema(
                doc_uuid=d.doc_uuid,
                title=d.title,
                owner_id=d.owner_id,
                owner_org=d.owner_org,
                source=d.source,
                source_url=d.source_url,
                status=_convert_status_to_api(d.status),
                security_level=_convert_security_to_api(d.security_level),
                chunk_count=d.chunk_count,
                created_at=d.created_at,
                updated_at=d.updated_at,
                metadata=d.metadata,
            )
            for d in docs
        ],
        total=len(docs),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{doc_uuid}",
    response_model=DocumentResponseSchema,
    summary="Get Document",
    description="""
Get a document by UUID.

Requires read access to the document.

**Authentication:**
- X-User-Id header is required
- X-User-Groups header is optional (comma-separated group names)
""",
    responses={
        200: {
            "description": "Document details",
            "model": DocumentResponseSchema,
        },
        403: {
            "description": "Access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Access denied"}
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found: doc-123"}
                }
            },
        },
    },
)
async def get_document(
    doc_uuid: str,
    x_user_id: str = Header(description="User ID"),
    x_user_groups: str | None = Header(description="Comma-separated group names", default=None),
    service: Any = Depends(get_document_service),
) -> DocumentResponseSchema:
    """Get a document by UUID.

    Args:
        doc_uuid: Document UUID
        service: Document service (injected)
        x_user_id: User ID from header
        x_user_groups: Comma-separated group names from header

    Returns:
        Document details

    Raises:
        HTTPException: 403 for access denied, 404 for not found
    """
    logger.debug(f"Get document: {doc_uuid} by user: {x_user_id}")

    groups = _parse_user_groups(x_user_groups)

    try:
        response = await service.get_document(
            doc_uuid=doc_uuid,
            user_id=x_user_id,
            user_groups=groups if groups else None,
        )

        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {doc_uuid}",
            )

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            owner_org=response.owner_org,
            source=response.source,
            source_url=response.source_url,
            status=_convert_status_to_api(response.status),
            security_level=_convert_security_to_api(response.security_level),
            chunk_count=response.chunk_count,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except PermissionError:
        logger.warning(f"Access denied: {x_user_id} -> {doc_uuid}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


@router.put(
    "/{doc_uuid}",
    response_model=DocumentResponseSchema,
    summary="Update Document",
    description="""
Update a document.

If content is provided, the document will be re-chunked and re-embedded.
Metadata updates are merged with existing metadata.

Requires write access to the document.

**Authentication:**
- X-User-Id header is required
- X-User-Groups header is optional (comma-separated group names)
""",
    responses={
        200: {
            "description": "Updated document",
            "model": DocumentResponseSchema,
        },
        400: {
            "description": "Invalid request",
            "content": {
                "application/json": {
                    "example": {"detail": "Content cannot be empty"}
                }
            },
        },
        403: {
            "description": "Access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Access denied"}
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found: doc-123"}
                }
            },
        },
    },
)
async def update_document(
    doc_uuid: str,
    request: DocumentUpdateSchema,
    x_user_id: str = Header(description="User ID"),
    x_user_groups: str | None = Header(description="Comma-separated group names", default=None),
    service: Any = Depends(get_document_service),
) -> DocumentResponseSchema:
    """Update a document.

    Args:
        doc_uuid: Document UUID
        request: Update request
        service: Document service (injected)
        x_user_id: User ID from header
        x_user_groups: Comma-separated group names from header

    Returns:
        Updated document

    Raises:
        HTTPException: 400 for invalid request, 403 for access denied, 404 for not found
    """
    logger.info(f"Update document: {doc_uuid} by user: {x_user_id}")

    groups = _parse_user_groups(x_user_groups)

    try:
        from src.services.document_service import DocumentUpdateRequest

        domain_request = DocumentUpdateRequest(
            title=request.title,
            content=request.content,
            status=_convert_status_to_domain(request.status),
            security_level=request.security_level.value if request.security_level else None,
            metadata=request.metadata,
        )

        response = await service.update_document(
            doc_uuid=doc_uuid,
            request=domain_request,
            user_id=x_user_id,
            user_groups=groups if groups else None,
        )

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            owner_org=response.owner_org,
            source=response.source,
            source_url=response.source_url,
            status=_convert_status_to_api(response.status),
            security_level=_convert_security_to_api(response.security_level),
            chunk_count=response.chunk_count,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except PermissionError:
        logger.warning(f"Access denied for update: {x_user_id} -> {doc_uuid}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )
        logger.warning(f"Invalid update request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Update document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document",
        )


@router.delete(
    "/{doc_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete Document",
    description="""
Delete a document and all associated data.

This operation:
1. Removes document from PostgreSQL
2. Removes vectors from Milvus
3. Removes graph nodes from Neo4j

Requires admin access to the document.

**Authentication:**
- X-User-Id header is required
- X-User-Groups header is optional (comma-separated group names)
""",
    responses={
        403: {
            "description": "Access denied",
            "content": {
                "application/json": {
                    "example": {"detail": "Access denied"}
                }
            },
        },
        404: {
            "description": "Document not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Document not found: doc-123"}
                }
            },
        },
    },
)
async def delete_document(
    doc_uuid: str,
    x_user_id: str = Header(description="User ID"),
    x_user_groups: str | None = Header(description="Comma-separated group names", default=None),
    service: Any = Depends(get_document_service),
) -> None:
    """Delete a document.

    Args:
        doc_uuid: Document UUID
        service: Document service (injected)
        x_user_id: User ID from header
        x_user_groups: Comma-separated group names from header

    Raises:
        HTTPException: 403 for access denied, 404 for not found
    """
    logger.info(f"Delete document: {doc_uuid} by user: {x_user_id}")

    groups = _parse_user_groups(x_user_groups)

    try:
        await service.delete_document(
            doc_uuid=doc_uuid,
            user_id=x_user_id,
            user_groups=groups if groups else None,
        )
    except PermissionError:
        logger.warning(f"Access denied for delete: {x_user_id} -> {doc_uuid}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except ValueError as e:
        logger.warning(f"Document not found for delete: {doc_uuid}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.exception(f"Delete document failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document",
        )
