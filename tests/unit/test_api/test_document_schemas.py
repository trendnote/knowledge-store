"""Tests for document API schemas."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.api.schemas.documents import (
    DocumentCreateSchema,
    DocumentListResponseSchema,
    DocumentResponseSchema,
    DocumentSourceEnum,
    DocumentStatusEnum,
    DocumentUpdateSchema,
    SecurityLevelEnum,
)


# =============================================================================
# Test Enums
# =============================================================================


class TestDocumentStatusEnum:
    """Tests for DocumentStatusEnum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert DocumentStatusEnum.DRAFT.value == "draft"
        assert DocumentStatusEnum.PUBLISHED.value == "published"
        assert DocumentStatusEnum.ARCHIVED.value == "archived"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert DocumentStatusEnum("draft") == DocumentStatusEnum.DRAFT
        assert DocumentStatusEnum("published") == DocumentStatusEnum.PUBLISHED


class TestDocumentSourceEnum:
    """Tests for DocumentSourceEnum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert DocumentSourceEnum.FILE.value == "file"
        assert DocumentSourceEnum.WIKI.value == "wiki"
        assert DocumentSourceEnum.CONFLUENCE.value == "confluence"


class TestSecurityLevelEnum:
    """Tests for SecurityLevelEnum."""

    def test_enum_values(self) -> None:
        """Test enum values."""
        assert SecurityLevelEnum.PUBLIC.value == "public"
        assert SecurityLevelEnum.INTERNAL.value == "internal"
        assert SecurityLevelEnum.CONFIDENTIAL.value == "confidential"


# =============================================================================
# Test DocumentCreateSchema
# =============================================================================


class TestDocumentCreateSchema:
    """Tests for DocumentCreateSchema."""

    def test_valid_minimal_request(self) -> None:
        """Test valid request with minimal fields."""
        schema = DocumentCreateSchema(
            title="Test Document",
            content="This is test content for the document.",
        )
        assert schema.title == "Test Document"
        assert schema.content == "This is test content for the document."
        assert schema.source == DocumentSourceEnum.FILE
        assert schema.security_level == SecurityLevelEnum.INTERNAL
        assert schema.chunk_size == 500
        assert schema.chunk_overlap == 50

    def test_valid_full_request(self) -> None:
        """Test valid request with all fields."""
        schema = DocumentCreateSchema(
            title="인공지능 기술 개요",
            content="인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.",
            source=DocumentSourceEnum.CONFLUENCE,
            source_url="https://example.com/doc.pdf",
            security_level=SecurityLevelEnum.CONFIDENTIAL,
            metadata={"department": "AI Lab"},
            chunk_size=800,
            chunk_overlap=100,
        )
        assert schema.title == "인공지능 기술 개요"
        assert schema.source == DocumentSourceEnum.CONFLUENCE
        assert schema.security_level == SecurityLevelEnum.CONFIDENTIAL
        assert schema.metadata["department"] == "AI Lab"
        assert schema.chunk_size == 800
        assert schema.chunk_overlap == 100

    def test_title_stripped(self) -> None:
        """Test that title is stripped."""
        schema = DocumentCreateSchema(
            title="  Test Title  ",
            content="Content",
        )
        assert schema.title == "Test Title"

    def test_title_empty_after_strip(self) -> None:
        """Test empty title after stripping fails."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentCreateSchema(title="   ", content="Content")
        assert "Title cannot be empty" in str(exc_info.value)

    def test_title_too_long(self) -> None:
        """Test title exceeding max length fails."""
        with pytest.raises(ValidationError):
            DocumentCreateSchema(
                title="A" * 501,
                content="Content",
            )

    def test_content_empty(self) -> None:
        """Test empty content fails."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentCreateSchema(title="Title", content="")
        # Should fail min_length validation
        assert "at least 1 character" in str(exc_info.value).lower() or \
               "string_too_short" in str(exc_info.value).lower()

    def test_content_whitespace_only(self) -> None:
        """Test whitespace-only content fails."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentCreateSchema(title="Title", content="   \n\t  ")
        assert "Content cannot be empty" in str(exc_info.value)

    def test_chunk_size_too_small(self) -> None:
        """Test chunk_size below minimum fails."""
        with pytest.raises(ValidationError):
            DocumentCreateSchema(
                title="Title",
                content="Content",
                chunk_size=50,  # Min is 100
            )

    def test_chunk_size_too_large(self) -> None:
        """Test chunk_size above maximum fails."""
        with pytest.raises(ValidationError):
            DocumentCreateSchema(
                title="Title",
                content="Content",
                chunk_size=3000,  # Max is 2000
            )

    def test_chunk_overlap_too_large(self) -> None:
        """Test chunk_overlap above maximum fails."""
        with pytest.raises(ValidationError):
            DocumentCreateSchema(
                title="Title",
                content="Content",
                chunk_overlap=250,  # Max is 200
            )


# =============================================================================
# Test DocumentUpdateSchema
# =============================================================================


class TestDocumentUpdateSchema:
    """Tests for DocumentUpdateSchema."""

    def test_all_none_valid(self) -> None:
        """Test all None fields is valid."""
        schema = DocumentUpdateSchema()
        assert schema.title is None
        assert schema.content is None
        assert schema.status is None
        assert schema.metadata is None

    def test_title_only(self) -> None:
        """Test title-only update."""
        schema = DocumentUpdateSchema(title="New Title")
        assert schema.title == "New Title"
        assert schema.content is None

    def test_content_only(self) -> None:
        """Test content-only update."""
        schema = DocumentUpdateSchema(content="New content here")
        assert schema.content == "New content here"
        assert schema.title is None

    def test_status_update(self) -> None:
        """Test status update."""
        schema = DocumentUpdateSchema(status=DocumentStatusEnum.PUBLISHED)
        assert schema.status == DocumentStatusEnum.PUBLISHED

    def test_title_stripped(self) -> None:
        """Test title is stripped."""
        schema = DocumentUpdateSchema(title="  New Title  ")
        assert schema.title == "New Title"

    def test_title_empty_after_strip(self) -> None:
        """Test empty title after stripping fails."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentUpdateSchema(title="   ")
        assert "Title cannot be empty" in str(exc_info.value)

    def test_content_whitespace_only(self) -> None:
        """Test whitespace-only content fails."""
        with pytest.raises(ValidationError) as exc_info:
            DocumentUpdateSchema(content="   \n  ")
        assert "Content cannot be empty" in str(exc_info.value)


# =============================================================================
# Test DocumentResponseSchema
# =============================================================================


class TestDocumentResponseSchema:
    """Tests for DocumentResponseSchema."""

    def test_valid_response(self) -> None:
        """Test valid response creation."""
        now = datetime.utcnow()
        response = DocumentResponseSchema(
            doc_uuid="550e8400-e29b-41d4-a716-446655440000",
            title="Test Document",
            owner_id="user123",
            owner_org="engineering",
            source="file",
            source_url="https://example.com/doc.pdf",
            status=DocumentStatusEnum.PUBLISHED,
            security_level=SecurityLevelEnum.INTERNAL,
            chunk_count=5,
            created_at=now,
            updated_at=now,
            metadata={"key": "value"},
        )
        assert response.doc_uuid == "550e8400-e29b-41d4-a716-446655440000"
        assert response.title == "Test Document"
        assert response.status == DocumentStatusEnum.PUBLISHED
        assert response.chunk_count == 5

    def test_minimal_response(self) -> None:
        """Test response with minimal fields."""
        response = DocumentResponseSchema(
            doc_uuid="doc-123",
            title="Test",
            owner_id="user1",
            owner_org="default",
            source="file",
            status=DocumentStatusEnum.DRAFT,
            security_level=SecurityLevelEnum.INTERNAL,
            chunk_count=0,
        )
        assert response.source_url is None
        assert response.created_at is None
        assert response.metadata == {}

    def test_chunk_count_non_negative(self) -> None:
        """Test chunk_count cannot be negative."""
        with pytest.raises(ValidationError):
            DocumentResponseSchema(
                doc_uuid="doc-123",
                title="Test",
                owner_id="user1",
                owner_org="default",
                source="file",
                status=DocumentStatusEnum.DRAFT,
                security_level=SecurityLevelEnum.INTERNAL,
                chunk_count=-1,
            )


# =============================================================================
# Test DocumentListResponseSchema
# =============================================================================


class TestDocumentListResponseSchema:
    """Tests for DocumentListResponseSchema."""

    def test_valid_list_response(self) -> None:
        """Test valid list response."""
        doc = DocumentResponseSchema(
            doc_uuid="doc-1",
            title="Doc 1",
            owner_id="user1",
            owner_org="default",
            source="file",
            status=DocumentStatusEnum.DRAFT,
            security_level=SecurityLevelEnum.INTERNAL,
            chunk_count=3,
        )
        response = DocumentListResponseSchema(
            documents=[doc],
            total=1,
            limit=20,
            offset=0,
        )
        assert len(response.documents) == 1
        assert response.total == 1
        assert response.limit == 20
        assert response.offset == 0

    def test_empty_list_response(self) -> None:
        """Test empty list response."""
        response = DocumentListResponseSchema(
            documents=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert len(response.documents) == 0
        assert response.total == 0

    def test_total_non_negative(self) -> None:
        """Test total cannot be negative."""
        with pytest.raises(ValidationError):
            DocumentListResponseSchema(
                documents=[],
                total=-1,
                limit=20,
                offset=0,
            )

    def test_limit_must_be_positive(self) -> None:
        """Test limit must be positive."""
        with pytest.raises(ValidationError):
            DocumentListResponseSchema(
                documents=[],
                total=0,
                limit=0,
                offset=0,
            )

    def test_offset_non_negative(self) -> None:
        """Test offset cannot be negative."""
        with pytest.raises(ValidationError):
            DocumentListResponseSchema(
                documents=[],
                total=0,
                limit=20,
                offset=-1,
            )
