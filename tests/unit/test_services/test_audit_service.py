"""Tests for audit service."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.audit import (
    AuditAction,
    AuditLogEntry,
    AuditQuery,
    ResourceType,
)
from src.services.audit_service import (
    AuditService,
    audit_document,
    audit_permission,
    audit_search,
    get_audit_service,
    set_audit_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create mock audit repository."""
    mock = MagicMock()
    mock.create_audit_log = AsyncMock(return_value=MagicMock(id=1))
    mock.create_audit_logs_batch = AsyncMock(return_value=1)
    mock.query_audit_logs = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def audit_service(mock_repository: MagicMock) -> AuditService:
    """Create audit service with mock repository."""
    return AuditService(
        repository=mock_repository,
        batch_size=10,
        flush_interval_seconds=1.0,
    )


@pytest.fixture(autouse=True)
def cleanup_global_service():
    """Reset global service after each test."""
    yield
    set_audit_service(None)


# =============================================================================
# Test AuditService Initialization
# =============================================================================


class TestAuditServiceInit:
    """Tests for AuditService initialization."""

    def test_default_values(self, mock_repository: MagicMock) -> None:
        """Test default configuration values."""
        service = AuditService(repository=mock_repository)

        assert service._batch_size == 100
        assert service._flush_interval == 5.0
        assert service._max_buffer_size == 10000
        assert service.buffer_size == 0
        assert service.is_started is False

    def test_custom_values(self, mock_repository: MagicMock) -> None:
        """Test custom configuration values."""
        service = AuditService(
            repository=mock_repository,
            batch_size=50,
            flush_interval_seconds=10.0,
            max_buffer_size=5000,
        )

        assert service._batch_size == 50
        assert service._flush_interval == 10.0
        assert service._max_buffer_size == 5000


# =============================================================================
# Test Lifecycle
# =============================================================================


class TestServiceLifecycle:
    """Tests for service lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, audit_service: AuditService) -> None:
        """Test starting the service."""
        await audit_service.start()

        assert audit_service.is_started is True
        assert audit_service._flush_task is not None

        await audit_service.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, audit_service: AuditService) -> None:
        """Test starting already started service."""
        await audit_service.start()
        task1 = audit_service._flush_task

        await audit_service.start()
        task2 = audit_service._flush_task

        # Should be same task
        assert task1 is task2

        await audit_service.stop()

    @pytest.mark.asyncio
    async def test_stop(self, audit_service: AuditService) -> None:
        """Test stopping the service."""
        await audit_service.start()
        await audit_service.stop()

        assert audit_service.is_started is False
        assert audit_service._flush_task is None

    @pytest.mark.asyncio
    async def test_stop_not_started(self, audit_service: AuditService) -> None:
        """Test stopping non-started service."""
        await audit_service.stop()

        assert audit_service.is_started is False


# =============================================================================
# Test Search Logging
# =============================================================================


class TestLogSearch:
    """Tests for search logging."""

    @pytest.mark.asyncio
    async def test_log_search_basic(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test basic search logging."""
        await audit_service.log_search(
            user_id="user1",
            query="test query",
            retrieved_docs=["doc1", "doc2"],
        )

        # Force flush
        await audit_service.flush()

        mock_repository.create_audit_logs_batch.assert_called_once()
        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert len(logs) == 1
        assert logs[0].user_id == "user1"
        assert logs[0].query_text == "test query"
        assert logs[0].retrieved_docs == ["doc1", "doc2"]
        assert logs[0].action == AuditAction.SEARCH_HYBRID

    @pytest.mark.asyncio
    async def test_log_search_with_type(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test search logging with different types."""
        await audit_service.log_search(
            user_id="user1",
            query="test",
            retrieved_docs=[],
            search_type="dense",
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.SEARCH_DENSE

    @pytest.mark.asyncio
    async def test_log_search_with_metadata(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test search logging with metadata."""
        await audit_service.log_search(
            user_id="user1",
            query="test",
            retrieved_docs=["doc1"],
            duration_ms=150.5,
            result_count=10,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].metadata["duration_ms"] == 150.5
        assert logs[0].metadata["result_count"] == 10
        assert logs[0].ip_address == "192.168.1.1"
        assert logs[0].user_agent == "TestAgent/1.0"


# =============================================================================
# Test Document Logging
# =============================================================================


class TestLogDocumentAccess:
    """Tests for document access logging."""

    @pytest.mark.asyncio
    async def test_log_document_read(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test document read logging."""
        await audit_service.log_document_access(
            user_id="user1",
            doc_uuid="doc-123",
            action=AuditAction.DOCUMENT_READ,
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.DOCUMENT_READ
        assert logs[0].resource_id == "doc-123"
        assert logs[0].resource_type == ResourceType.DOCUMENT

    @pytest.mark.asyncio
    async def test_log_document_create(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test document create logging."""
        await audit_service.log_document_access(
            user_id="user1",
            doc_uuid="doc-123",
            action=AuditAction.DOCUMENT_CREATE,
            metadata={"title": "New Doc"},
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.DOCUMENT_CREATE
        assert logs[0].metadata["title"] == "New Doc"

    @pytest.mark.asyncio
    async def test_log_document_delete(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test document delete logging."""
        await audit_service.log_document_access(
            user_id="user1",
            doc_uuid="doc-123",
            action=AuditAction.DOCUMENT_DELETE,
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.DOCUMENT_DELETE


# =============================================================================
# Test Permission Logging
# =============================================================================


class TestLogPermissionChange:
    """Tests for permission change logging."""

    @pytest.mark.asyncio
    async def test_log_permission_grant(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test permission grant logging."""
        await audit_service.log_permission_change(
            user_id="admin1",
            doc_uuid="doc-123",
            action=AuditAction.PERMISSION_GRANT,
            principal_type="user",
            principal_id="user2",
            permission="read",
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.PERMISSION_GRANT
        assert logs[0].resource_type == ResourceType.PERMISSION
        assert logs[0].metadata["principal_type"] == "user"
        assert logs[0].metadata["principal_id"] == "user2"
        assert logs[0].metadata["permission"] == "read"

    @pytest.mark.asyncio
    async def test_log_permission_revoke(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test permission revoke logging."""
        await audit_service.log_permission_change(
            user_id="admin1",
            doc_uuid="doc-123",
            action=AuditAction.PERMISSION_REVOKE,
            principal_type="group",
            principal_id="team-a",
            permission="write",
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.PERMISSION_REVOKE


# =============================================================================
# Test Export Logging
# =============================================================================


class TestLogExport:
    """Tests for export logging."""

    @pytest.mark.asyncio
    async def test_log_export(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test export logging."""
        await audit_service.log_export(
            user_id="user1",
            doc_uuid="doc-123",
            export_format="pdf",
        )
        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.EXPORT
        assert logs[0].metadata["export_format"] == "pdf"


# =============================================================================
# Test Batch Processing
# =============================================================================


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.mark.asyncio
    async def test_batch_flush_on_size(
        self,
        mock_repository: MagicMock,
    ) -> None:
        """Test automatic flush when batch size reached."""
        service = AuditService(
            repository=mock_repository,
            batch_size=2,
            flush_interval_seconds=60.0,  # Long interval
        )

        await service.log_search("user1", "q1", [])
        await service.log_search("user1", "q2", [])

        # Wait for async flush
        await asyncio.sleep(0.1)

        mock_repository.create_audit_logs_batch.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_logs_batched(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test multiple logs are batched together."""
        await audit_service.log_search("user1", "q1", [])
        await audit_service.log_search("user2", "q2", [])
        await audit_service.log_document_access(
            "user3", "doc-1", AuditAction.DOCUMENT_READ
        )

        await audit_service.flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert len(logs) == 3

    @pytest.mark.asyncio
    async def test_empty_flush(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test flushing empty buffer."""
        await audit_service.flush()

        mock_repository.create_audit_logs_batch.assert_not_called()


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_flush_error_retains_logs(
        self,
        mock_repository: MagicMock,
    ) -> None:
        """Test logs are retained on flush error."""
        mock_repository.create_audit_logs_batch = AsyncMock(
            side_effect=Exception("DB error")
        )

        service = AuditService(
            repository=mock_repository,
            batch_size=100,
        )

        await service.log_search("user1", "test", [])
        initial_size = service.buffer_size

        await service.flush()

        # Logs should be back in buffer
        assert service.buffer_size == initial_size


# =============================================================================
# Test Query
# =============================================================================


class TestQueryLogs:
    """Tests for querying logs."""

    @pytest.mark.asyncio
    async def test_query_logs(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test querying audit logs."""
        expected_logs = [
            AuditLogEntry(
                user_id="user1",
                action=AuditAction.SEARCH,
                resource_type=ResourceType.SEARCH,
            )
        ]
        mock_repository.query_audit_logs = AsyncMock(return_value=expected_logs)

        query = AuditQuery(user_id="user1")
        logs = await audit_service.query_logs(query)

        assert logs == expected_logs
        mock_repository.query_audit_logs.assert_called_once_with(query)


# =============================================================================
# Test Global Functions
# =============================================================================


class TestGlobalFunctions:
    """Tests for global audit functions."""

    def test_get_set_audit_service(self, audit_service: AuditService) -> None:
        """Test getting and setting global service."""
        assert get_audit_service() is None

        set_audit_service(audit_service)
        assert get_audit_service() is audit_service

        set_audit_service(None)
        assert get_audit_service() is None

    @pytest.mark.asyncio
    async def test_audit_search_with_service(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test audit_search with global service."""
        set_audit_service(audit_service)

        await audit_search(
            user_id="user1",
            query="test",
            retrieved_docs=["doc1"],
        )
        await audit_service.flush()

        mock_repository.create_audit_logs_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_search_without_service(self) -> None:
        """Test audit_search without global service."""
        # Should not raise
        await audit_search(
            user_id="user1",
            query="test",
            retrieved_docs=[],
        )

    @pytest.mark.asyncio
    async def test_audit_document_with_service(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test audit_document with global service."""
        set_audit_service(audit_service)

        await audit_document(
            user_id="user1",
            doc_uuid="doc-123",
            action=AuditAction.DOCUMENT_READ,
        )
        await audit_service.flush()

        mock_repository.create_audit_logs_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_permission_with_service(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test audit_permission with global service."""
        set_audit_service(audit_service)

        await audit_permission(
            user_id="admin1",
            doc_uuid="doc-123",
            action=AuditAction.PERMISSION_GRANT,
            principal_type="user",
            principal_id="user2",
            permission="read",
        )
        await audit_service.flush()

        mock_repository.create_audit_logs_batch.assert_called_once()
