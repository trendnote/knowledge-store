"""Document API schemas.

This module defines Pydantic schemas for Document API endpoints:
- DocumentCreateSchema: For creating documents
- DocumentUpdateSchema: For updating documents
- DocumentResponseSchema: For document responses
- DocumentListResponseSchema: For paginated document lists

All schemas include validation and documentation for OpenAPI generation.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums
# =============================================================================


class DocumentStatusEnum(str, Enum):
    """Document status enum for API layer."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DocumentSourceEnum(str, Enum):
    """Document source enum for API layer."""

    WIKI = "wiki"
    AGIT = "agit"
    GDOCS = "gdocs"
    SLACK = "slack"
    CONFLUENCE = "confluence"
    NOTION = "notion"
    FILE = "file"


class SecurityLevelEnum(str, Enum):
    """Security level enum for API layer."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"


# =============================================================================
# Request Schemas
# =============================================================================


class DocumentCreateSchema(BaseModel):
    """Schema for creating a document.

    Attributes:
        title: Document title (1-500 characters)
        content: Document content to be chunked and embedded
        source: Source system (wiki, agit, gdocs, etc.)
        source_url: Original document URL
        security_level: Security classification
        metadata: Additional metadata
        chunk_size: Characters per chunk (100-2000)
        chunk_overlap: Overlap between chunks (0-200)
    """

    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Document title",
        examples=["인공지능 기술 개요"],
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Document content to be chunked and embedded",
    )
    source: DocumentSourceEnum = Field(
        default=DocumentSourceEnum.FILE,
        description="Source system of the document",
    )
    source_url: str | None = Field(
        None,
        description="Source URL of the document",
        examples=["https://example.com/doc.pdf"],
    )
    security_level: SecurityLevelEnum = Field(
        default=SecurityLevelEnum.INTERNAL,
        description="Security classification level",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Maximum characters per chunk",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=200,
        description="Overlap between consecutive chunks",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate and strip title.

        Args:
            v: Title value

        Returns:
            Stripped title

        Raises:
            ValueError: If title is empty after stripping
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty")
        return stripped

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not just whitespace.

        Args:
            v: Content value

        Returns:
            Original content

        Raises:
            ValueError: If content is empty or whitespace only
        """
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace only")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "인공지능 기술 개요",
                    "content": "인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다...",
                    "source": "file",
                    "source_url": "https://example.com/ai-overview.pdf",
                    "security_level": "internal",
                    "metadata": {"department": "engineering"},
                    "chunk_size": 500,
                    "chunk_overlap": 50,
                }
            ]
        }
    }


class DocumentUpdateSchema(BaseModel):
    """Schema for updating a document.

    All fields are optional. Only provided fields will be updated.
    Content changes trigger re-chunking and re-embedding.

    Attributes:
        title: New document title
        content: New content (triggers re-chunking)
        status: New status
        security_level: New security level
        metadata: Metadata to merge with existing
    """

    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="New document title",
    )
    content: str | None = Field(
        None,
        min_length=1,
        description="New content (triggers re-chunking if provided)",
    )
    status: DocumentStatusEnum | None = Field(
        None,
        description="New document status",
    )
    security_level: SecurityLevelEnum | None = Field(
        None,
        description="New security classification",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Metadata to merge with existing metadata",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Validate and strip title if provided."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title cannot be empty")
        return stripped

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str | None) -> str | None:
        """Validate content is not whitespace if provided."""
        if v is None:
            return None
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace only")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "인공지능 기술 개요 (수정판)",
                    "status": "published",
                },
                {
                    "content": "새로운 내용으로 업데이트...",
                },
            ]
        }
    }


# =============================================================================
# Response Schemas
# =============================================================================


class DocumentResponseSchema(BaseModel):
    """Document response schema.

    Attributes:
        doc_uuid: Unique document identifier
        title: Document title
        owner_id: Owner user ID
        owner_org: Owner organization
        source: Source system
        source_url: Original document URL
        status: Document status
        security_level: Security classification
        chunk_count: Number of chunks
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: Additional metadata
    """

    doc_uuid: str = Field(..., description="Document UUID")
    title: str = Field(..., description="Document title")
    owner_id: str = Field(..., description="Owner user ID")
    owner_org: str = Field(..., description="Owner organization")
    source: str = Field(..., description="Source system")
    source_url: str | None = Field(None, description="Source URL")
    status: DocumentStatusEnum = Field(..., description="Document status")
    security_level: SecurityLevelEnum = Field(
        ..., description="Security classification"
    )
    chunk_count: int = Field(..., ge=0, description="Number of chunks")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "인공지능 기술 개요",
                    "owner_id": "user123",
                    "owner_org": "engineering",
                    "source": "file",
                    "source_url": "https://example.com/ai.pdf",
                    "status": "published",
                    "security_level": "internal",
                    "chunk_count": 5,
                    "created_at": "2026-01-26T10:00:00Z",
                    "updated_at": "2026-01-26T11:00:00Z",
                    "metadata": {"department": "AI Lab"},
                }
            ]
        }
    }


class DocumentListResponseSchema(BaseModel):
    """Paginated list of documents response.

    Attributes:
        documents: List of document responses
        total: Total number of documents in this response
        limit: Maximum documents per page
        offset: Pagination offset
    """

    documents: list[DocumentResponseSchema] = Field(
        ..., description="List of documents"
    )
    total: int = Field(..., ge=0, description="Total documents in response")
    limit: int = Field(..., ge=1, description="Maximum documents per page")
    offset: int = Field(..., ge=0, description="Pagination offset")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "documents": [
                        {
                            "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
                            "title": "인공지능 기술 개요",
                            "owner_id": "user123",
                            "owner_org": "engineering",
                            "source": "file",
                            "status": "published",
                            "security_level": "internal",
                            "chunk_count": 5,
                            "created_at": "2026-01-26T10:00:00Z",
                            "updated_at": "2026-01-26T11:00:00Z",
                        }
                    ],
                    "total": 1,
                    "limit": 20,
                    "offset": 0,
                }
            ]
        }
    }


# =============================================================================
# Error Schemas
# =============================================================================


class DocumentErrorSchema(BaseModel):
    """Error response schema.

    Attributes:
        detail: Error message
        error_code: Optional error code for client handling
    """

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Error code")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"detail": "Document not found: doc-123"},
                {"detail": "Access denied", "error_code": "FORBIDDEN"},
            ]
        }
    }
