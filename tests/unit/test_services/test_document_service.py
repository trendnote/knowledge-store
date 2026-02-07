"""Tests for document service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

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


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_postgres_repo() -> MagicMock:
    """Create mock PostgreSQL repository."""
    repo = MagicMock()
    repo.get_document = AsyncMock(return_value=None)
    repo.create_document = AsyncMock()
    repo.update_document = AsyncMock()
    repo.delete_document = AsyncMock(return_value=True)
    repo.list_documents = AsyncMock(return_value=[])
    repo.get_chunks_by_doc = AsyncMock(return_value=[])
    repo.create_chunks = AsyncMock(return_value=[])
    repo.get_next_version_no = AsyncMock(return_value=1)
    return repo


@pytest.fixture
def mock_saga_coordinator() -> MagicMock:
    """Create mock saga coordinator."""
    saga = MagicMock()
    saga.execute_create_saga = AsyncMock(
        return_value=MagicMock(success=True, error=None)
    )
    saga.execute_update_saga = AsyncMock(
        return_value=MagicMock(success=True, error=None)
    )
    saga.execute_delete_saga = AsyncMock(
        return_value=MagicMock(success=True, error=None)
    )
    return saga


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    service = MagicMock()
    service.encode = MagicMock(return_value=MagicMock(dense=[[0.1] * 1024]))
    return service


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Create mock Kafka producer."""
    producer = MagicMock()
    producer.send = AsyncMock()
    return producer


@pytest.fixture
def mock_acl_service() -> MagicMock:
    """Create mock ACL service."""
    acl = MagicMock()
    acl.check_access = AsyncMock(return_value=True)
    acl.grant_access = AsyncMock()
    acl.get_accessible_documents = AsyncMock(return_value=["doc-1", "doc-2"])
    return acl


@pytest.fixture
def document_service(
    mock_postgres_repo: MagicMock,
    mock_saga_coordinator: MagicMock,
    mock_embedding_service: MagicMock,
    mock_kafka_producer: MagicMock,
    mock_acl_service: MagicMock,
) -> DocumentService:
    """Create document service with all mocks."""
    return DocumentService(
        postgres_repo=mock_postgres_repo,
        saga_coordinator=mock_saga_coordinator,
        embedding_service=mock_embedding_service,
        kafka_producer=mock_kafka_producer,
        acl_service=mock_acl_service,
    )


@pytest.fixture
def document_service_minimal(
    mock_postgres_repo: MagicMock,
    mock_saga_coordinator: MagicMock,
    mock_embedding_service: MagicMock,
) -> DocumentService:
    """Create document service without optional dependencies."""
    return DocumentService(
        postgres_repo=mock_postgres_repo,
        saga_coordinator=mock_saga_coordinator,
        embedding_service=mock_embedding_service,
    )


# =============================================================================
# Test Text Chunking
# =============================================================================


class TestTextChunking:
    """Tests for text chunking functionality."""

    def test_chunk_text_empty(
        self, document_service: DocumentService
    ) -> None:
        """Test chunking empty text returns empty list."""
        result = document_service._chunk_text("")
        assert result == []

    def test_chunk_text_whitespace_only(
        self, document_service: DocumentService
    ) -> None:
        """Test chunking whitespace-only text returns empty list."""
        result = document_service._chunk_text("   \n\t  ")
        assert result == []

    def test_chunk_text_simple(
        self, document_service: DocumentService
    ) -> None:
        """Test simple text chunking."""
        text = "A" * 1000
        result = document_service._chunk_text(text, chunk_size=300, chunk_overlap=50)

        assert len(result) > 1
        # Each chunk should have text and positions
        for chunk_text, start, end in result:
            assert len(chunk_text) <= 300
            assert start >= 0
            assert end > start

    def test_chunk_text_with_sentence_boundary(
        self, document_service: DocumentService
    ) -> None:
        """Test chunking respects sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = document_service._chunk_text(text, chunk_size=40, chunk_overlap=10)

        # Should have multiple chunks
        assert len(result) >= 1
        # Check that chunks contain sentence-like content
        all_text = "".join(chunk for chunk, _, _ in result)
        assert "sentence" in all_text

    def test_chunk_text_with_paragraphs(
        self, document_service: DocumentService
    ) -> None:
        """Test chunking respects paragraph boundaries."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = document_service._chunk_text(text, chunk_size=30, chunk_overlap=5)

        assert len(result) >= 2

    def test_chunk_text_small_content(
        self, document_service: DocumentService
    ) -> None:
        """Test chunking small content produces single chunk."""
        text = "Short text."
        result = document_service._chunk_text(text, chunk_size=500, chunk_overlap=50)

        assert len(result) == 1
        assert result[0][0] == "Short text."

    def test_create_chunks(
        self, document_service: DocumentService
    ) -> None:
        """Test creating ChunkData objects from content."""
        doc_uuid = str(uuid4())
        version_id = str(uuid4())
        content = "This is test content for chunking. " * 50

        chunks = document_service._create_chunks(
            doc_uuid=doc_uuid,
            version_id=version_id,
            content=content,
            chunk_size=200,
            chunk_overlap=20,
        )

        assert len(chunks) > 1
        for i, chunk in enumerate(chunks):
            assert chunk.doc_uuid == doc_uuid
            assert chunk.version_id == version_id
            assert chunk.chunk_no == i
            assert len(chunk.chunk_uuid) > 0
            assert len(chunk.chunk_text) > 0


# =============================================================================
# Test Create Document
# =============================================================================


class TestCreateDocument:
    """Tests for document creation."""

    @pytest.mark.asyncio
    async def test_create_document_success(
        self,
        document_service: DocumentService,
        mock_saga_coordinator: MagicMock,
        mock_acl_service: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test successful document creation."""
        request = DocumentCreateRequest(
            title="Test Document",
            content="This is test content for the document. " * 20,
            owner_id="user1",
            owner_org="org1",
        )

        response = await document_service.create_document(request)

        assert response.title == "Test Document"
        assert response.owner_id == "user1"
        assert response.owner_org == "org1"
        assert response.status == "draft"
        assert response.chunk_count > 0
        assert response.doc_uuid is not None

        # Verify saga was called
        mock_saga_coordinator.execute_create_saga.assert_called_once()

        # Verify ACL grant was called
        mock_acl_service.grant_access.assert_called_once()

        # Verify Kafka event was published
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "document.created"

    @pytest.mark.asyncio
    async def test_create_document_empty_content(
        self, document_service: DocumentService
    ) -> None:
        """Test create with empty content fails."""
        request = DocumentCreateRequest(
            title="Test",
            content="",
            owner_id="user1",
        )

        with pytest.raises(ValueError, match="content cannot be empty"):
            await document_service.create_document(request)

    @pytest.mark.asyncio
    async def test_create_document_whitespace_content(
        self, document_service: DocumentService
    ) -> None:
        """Test create with whitespace-only content fails."""
        request = DocumentCreateRequest(
            title="Test",
            content="   \n\t  ",
            owner_id="user1",
        )

        with pytest.raises(ValueError, match="content cannot be empty"):
            await document_service.create_document(request)

    @pytest.mark.asyncio
    async def test_create_document_saga_failure(
        self,
        document_service: DocumentService,
        mock_saga_coordinator: MagicMock,
    ) -> None:
        """Test create fails when saga fails."""
        mock_saga_coordinator.execute_create_saga = AsyncMock(
            return_value=MagicMock(success=False, error="Milvus connection failed")
        )

        request = DocumentCreateRequest(
            title="Test",
            content="Test content " * 20,
            owner_id="user1",
        )

        with pytest.raises(RuntimeError, match="Failed to create document"):
            await document_service.create_document(request)

    @pytest.mark.asyncio
    async def test_create_document_without_optional_deps(
        self,
        document_service_minimal: DocumentService,
        mock_saga_coordinator: MagicMock,
    ) -> None:
        """Test create works without Kafka and ACL."""
        request = DocumentCreateRequest(
            title="Test",
            content="Test content " * 20,
            owner_id="user1",
        )

        response = await document_service_minimal.create_document(request)

        assert response.title == "Test"
        assert response.owner_id == "user1"


# =============================================================================
# Test Get Document
# =============================================================================


class TestGetDocument:
    """Tests for document retrieval."""

    @pytest.mark.asyncio
    async def test_get_document_success(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
    ) -> None:
        """Test successful document retrieval."""
        doc_uuid = str(uuid4())
        mock_doc = MagicMock()
        mock_doc.doc_uuid = doc_uuid
        mock_doc.title = "Test Doc"
        mock_doc.owner_id = "user1"
        mock_doc.owner_org = "org1"
        mock_doc.source = "file"
        mock_doc.source_url = None
        mock_doc.status = "published"
        mock_doc.security_level = "internal"
        mock_doc.created_at = datetime.utcnow()
        mock_doc.updated_at = datetime.utcnow()

        mock_postgres_repo.get_document = AsyncMock(return_value=mock_doc)
        mock_postgres_repo.get_chunks_by_doc = AsyncMock(
            return_value=[MagicMock(), MagicMock()]
        )

        response = await document_service.get_document(doc_uuid, "user1")

        assert response is not None
        assert response.title == "Test Doc"
        assert response.chunk_count == 2

    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
    ) -> None:
        """Test get returns None when document not found."""
        mock_postgres_repo.get_document = AsyncMock(return_value=None)

        response = await document_service.get_document("nonexistent", "user1")

        assert response is None

    @pytest.mark.asyncio
    async def test_get_document_access_denied(
        self,
        document_service: DocumentService,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test get fails when access denied."""
        mock_acl_service.check_access = AsyncMock(return_value=False)

        with pytest.raises(PermissionError, match="does not have read access"):
            await document_service.get_document("doc-uuid", "user1")


# =============================================================================
# Test List Documents
# =============================================================================


class TestListDocuments:
    """Tests for document listing."""

    @pytest.mark.asyncio
    async def test_list_documents_success(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test successful document listing."""
        doc1 = MagicMock()
        doc1.doc_uuid = "doc-1"
        doc1.title = "Doc 1"
        doc1.owner_id = "user1"
        doc1.owner_org = "org1"
        doc1.source = "file"
        doc1.source_url = None
        doc1.status = "published"
        doc1.security_level = "internal"
        doc1.created_at = datetime.utcnow()
        doc1.updated_at = datetime.utcnow()

        mock_acl_service.get_accessible_documents = AsyncMock(return_value=["doc-1"])
        mock_postgres_repo.list_documents = AsyncMock(return_value=[doc1])
        mock_postgres_repo.get_chunks_by_doc = AsyncMock(return_value=[MagicMock()])

        response = await document_service.list_documents("user1")

        assert len(response) == 1
        assert response[0].title == "Doc 1"

    @pytest.mark.asyncio
    async def test_list_documents_empty_access(
        self,
        document_service: DocumentService,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test list returns empty when no access."""
        mock_acl_service.get_accessible_documents = AsyncMock(return_value=[])

        response = await document_service.list_documents("user1")

        assert response == []


# =============================================================================
# Test Update Document
# =============================================================================


class TestUpdateDocument:
    """Tests for document update."""

    @pytest.mark.asyncio
    async def test_update_document_metadata_only(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test update without content change."""
        doc_uuid = str(uuid4())
        mock_doc = MagicMock()
        mock_doc.doc_uuid = doc_uuid
        mock_doc.title = "Original Title"
        mock_doc.owner_id = "user1"
        mock_doc.owner_org = "org1"
        mock_doc.source = "file"
        mock_doc.source_url = None
        mock_doc.status = "draft"
        mock_doc.security_level = "internal"
        mock_doc.created_at = datetime.utcnow()
        mock_doc.updated_at = datetime.utcnow()

        mock_postgres_repo.get_document = AsyncMock(return_value=mock_doc)
        mock_postgres_repo.get_chunks_by_doc = AsyncMock(return_value=[MagicMock()])

        # Update after update_document call
        updated_doc = MagicMock()
        updated_doc.doc_uuid = doc_uuid
        updated_doc.title = "New Title"
        updated_doc.owner_id = "user1"
        updated_doc.owner_org = "org1"
        updated_doc.source = "file"
        updated_doc.source_url = None
        updated_doc.status = "draft"
        updated_doc.security_level = "internal"
        updated_doc.created_at = datetime.utcnow()
        updated_doc.updated_at = datetime.utcnow()

        mock_postgres_repo.get_document = AsyncMock(
            side_effect=[mock_doc, updated_doc]
        )

        request = DocumentUpdateRequest(title="New Title")
        response = await document_service.update_document(doc_uuid, request, "user1")

        assert response.title == "New Title"
        mock_postgres_repo.update_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_document_with_content(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
        mock_saga_coordinator: MagicMock,
    ) -> None:
        """Test update with content change triggers saga."""
        doc_uuid = str(uuid4())
        mock_doc = MagicMock()
        mock_doc.doc_uuid = doc_uuid
        mock_doc.title = "Title"
        mock_doc.owner_id = "user1"
        mock_doc.owner_org = "org1"
        mock_doc.source = "file"
        mock_doc.source_url = None
        mock_doc.status = "draft"
        mock_doc.security_level = "internal"
        mock_doc.created_at = datetime.utcnow()
        mock_doc.updated_at = datetime.utcnow()

        mock_postgres_repo.get_document = AsyncMock(return_value=mock_doc)

        request = DocumentUpdateRequest(content="New content " * 20)
        response = await document_service.update_document(doc_uuid, request, "user1")

        mock_saga_coordinator.execute_update_saga.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_document_not_found(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
    ) -> None:
        """Test update fails when document not found."""
        mock_postgres_repo.get_document = AsyncMock(return_value=None)

        request = DocumentUpdateRequest(title="New Title")

        with pytest.raises(ValueError, match="Document not found"):
            await document_service.update_document("doc-uuid", request, "user1")

    @pytest.mark.asyncio
    async def test_update_document_access_denied(
        self,
        document_service: DocumentService,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test update fails when access denied."""
        mock_acl_service.check_access = AsyncMock(return_value=False)

        request = DocumentUpdateRequest(title="New Title")

        with pytest.raises(PermissionError, match="does not have write access"):
            await document_service.update_document("doc-uuid", request, "user1")


# =============================================================================
# Test Delete Document
# =============================================================================


class TestDeleteDocument:
    """Tests for document deletion."""

    @pytest.mark.asyncio
    async def test_delete_document_success(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
        mock_saga_coordinator: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test successful document deletion."""
        doc_uuid = str(uuid4())
        mock_doc = MagicMock()
        mock_doc.doc_uuid = doc_uuid
        mock_doc.title = "Test Doc"

        mock_postgres_repo.get_document = AsyncMock(return_value=mock_doc)

        result = await document_service.delete_document(doc_uuid, "user1")

        assert result is True
        mock_saga_coordinator.execute_delete_saga.assert_called_once_with(doc_uuid)

        # Verify Kafka event
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "document.deleted"

    @pytest.mark.asyncio
    async def test_delete_document_not_found(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
    ) -> None:
        """Test delete fails when document not found."""
        mock_postgres_repo.get_document = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Document not found"):
            await document_service.delete_document("doc-uuid", "user1")

    @pytest.mark.asyncio
    async def test_delete_document_access_denied(
        self,
        document_service: DocumentService,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test delete fails when access denied."""
        mock_acl_service.check_access = AsyncMock(return_value=False)

        with pytest.raises(PermissionError, match="does not have admin access"):
            await document_service.delete_document("doc-uuid", "user1")

    @pytest.mark.asyncio
    async def test_delete_document_saga_failure(
        self,
        document_service: DocumentService,
        mock_postgres_repo: MagicMock,
        mock_saga_coordinator: MagicMock,
    ) -> None:
        """Test delete fails when saga fails."""
        mock_doc = MagicMock()
        mock_doc.title = "Test"
        mock_postgres_repo.get_document = AsyncMock(return_value=mock_doc)
        mock_saga_coordinator.execute_delete_saga = AsyncMock(
            return_value=MagicMock(success=False, error="Neo4j unavailable")
        )

        with pytest.raises(RuntimeError, match="Failed to delete document"):
            await document_service.delete_document("doc-uuid", "user1")


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory and singleton functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_document_service()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_document_service()

    def test_get_document_service_requires_deps(self) -> None:
        """Test get_document_service requires dependencies on first call."""
        with pytest.raises(ValueError, match="required"):
            get_document_service()

    def test_get_document_service_singleton(
        self,
        mock_postgres_repo: MagicMock,
        mock_saga_coordinator: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test get_document_service returns same instance."""
        service1 = get_document_service(
            postgres_repo=mock_postgres_repo,
            saga_coordinator=mock_saga_coordinator,
            embedding_service=mock_embedding_service,
        )
        service2 = get_document_service()

        assert service1 is service2

    def test_set_document_service(self) -> None:
        """Test set_document_service sets singleton."""
        mock_service = MagicMock(spec=DocumentService)
        set_document_service(mock_service)

        service = get_document_service()
        assert service is mock_service

    def test_reset_document_service(
        self,
        mock_postgres_repo: MagicMock,
        mock_saga_coordinator: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test reset_document_service clears singleton."""
        service1 = get_document_service(
            postgres_repo=mock_postgres_repo,
            saga_coordinator=mock_saga_coordinator,
            embedding_service=mock_embedding_service,
        )

        reset_document_service()

        service2 = get_document_service(
            postgres_repo=mock_postgres_repo,
            saga_coordinator=mock_saga_coordinator,
            embedding_service=mock_embedding_service,
        )

        assert service1 is not service2


# =============================================================================
# Test Content Hash
# =============================================================================


class TestContentHash:
    """Tests for content hashing."""

    def test_compute_content_hash(
        self, document_service: DocumentService
    ) -> None:
        """Test content hash computation."""
        content = "Test content"
        hash1 = document_service._compute_content_hash(content)

        assert len(hash1) == 64  # SHA-256 hex digest
        assert hash1.isalnum()

    def test_compute_content_hash_deterministic(
        self, document_service: DocumentService
    ) -> None:
        """Test content hash is deterministic."""
        content = "Same content"
        hash1 = document_service._compute_content_hash(content)
        hash2 = document_service._compute_content_hash(content)

        assert hash1 == hash2

    def test_compute_content_hash_different_content(
        self, document_service: DocumentService
    ) -> None:
        """Test different content produces different hash."""
        hash1 = document_service._compute_content_hash("Content 1")
        hash2 = document_service._compute_content_hash("Content 2")

        assert hash1 != hash2
