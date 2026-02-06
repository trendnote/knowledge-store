"""Tests for PostgreSQL repository."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domain.document import AclEntry, AuditLog, Chunk, Document, DocumentVersion
from src.repositories.postgres.repository import (
    PostgresRepository,
    get_postgres_repository,
    reset_postgres_repository,
)


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock PostgreSQL client."""
    client = MagicMock()
    client.fetchrow = AsyncMock()
    client.fetch = AsyncMock()
    client.fetchval = AsyncMock()
    client.execute = AsyncMock()

    # Mock transaction context manager
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock()
    mock_conn.execute = AsyncMock()

    mock_transaction = MagicMock()
    mock_transaction.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_transaction.__aexit__ = AsyncMock(return_value=None)

    client.transaction.return_value = mock_transaction
    client._mock_conn = mock_conn  # Store for test access

    return client


@pytest.fixture
def repo(mock_client: MagicMock) -> PostgresRepository:
    """Create repository with mock client."""
    return PostgresRepository(mock_client)


class TestDocumentCRUD:
    """Tests for Document CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_document(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test document creation."""
        doc = Document(
            title="Test Doc",
            source="wiki",
            source_url="http://example.com",
            owner_id="user1",
            owner_org="org1",
        )

        doc_uuid = uuid4()
        now = datetime.now()
        mock_client.fetchrow.return_value = {
            "doc_uuid": doc_uuid,
            "created_at": now,
            "updated_at": now,
        }

        result = await repo.create_document(doc)

        assert result.doc_uuid == doc_uuid
        assert result.title == doc.title
        assert result.source == doc.source
        assert result.created_at == now
        mock_client.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_document_found(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting existing document."""
        doc_uuid = uuid4()
        mock_client.fetchrow.return_value = {
            "doc_uuid": doc_uuid,
            "title": "Test",
            "source": "wiki",
            "source_url": "http://test.com",
            "owner_id": "user1",
            "owner_org": "org1",
            "status": "draft",
            "security_level": "internal",
            "current_version_id": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        result = await repo.get_document(doc_uuid)

        assert result is not None
        assert result.doc_uuid == doc_uuid
        assert result.title == "Test"

    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting non-existent document."""
        mock_client.fetchrow.return_value = None

        result = await repo.get_document(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_update_document(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test updating document."""
        doc_uuid = uuid4()
        mock_client.fetchrow.return_value = {
            "doc_uuid": doc_uuid,
            "title": "Updated Title",
            "source": "wiki",
            "source_url": "http://test.com",
            "owner_id": "user1",
            "owner_org": "org1",
            "status": "published",
            "security_level": "internal",
            "current_version_id": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        result = await repo.update_document(
            doc_uuid, {"title": "Updated Title", "status": "published"}
        )

        assert result is not None
        assert result.title == "Updated Title"
        assert result.status == "published"

    @pytest.mark.asyncio
    async def test_update_document_empty_updates(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test update with empty updates returns current document."""
        doc_uuid = uuid4()
        mock_client.fetchrow.return_value = {
            "doc_uuid": doc_uuid,
            "title": "Test",
            "source": "wiki",
            "source_url": "http://test.com",
            "owner_id": "user1",
            "owner_org": "org1",
            "status": "draft",
            "security_level": "internal",
            "current_version_id": None,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        result = await repo.update_document(doc_uuid, {})

        assert result is not None
        assert result.doc_uuid == doc_uuid

    @pytest.mark.asyncio
    async def test_delete_document_found(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting existing document."""
        doc_uuid = uuid4()
        mock_client.fetchrow.return_value = {"doc_uuid": doc_uuid}

        result = await repo.delete_document(doc_uuid)

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_document_not_found(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting non-existent document."""
        mock_client.fetchrow.return_value = None

        result = await repo.delete_document(uuid4())

        assert result is False

    @pytest.mark.asyncio
    async def test_list_documents(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test listing documents."""
        doc_uuid = uuid4()
        mock_client.fetch.return_value = [
            {
                "doc_uuid": doc_uuid,
                "title": "Doc 1",
                "source": "wiki",
                "source_url": "http://test.com",
                "owner_id": "user1",
                "owner_org": "org1",
                "status": "draft",
                "security_level": "internal",
                "current_version_id": None,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            }
        ]

        result = await repo.list_documents(limit=10, status="draft")

        assert len(result) == 1
        assert result[0].doc_uuid == doc_uuid

    @pytest.mark.asyncio
    async def test_count_documents(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test counting documents."""
        mock_client.fetchval.return_value = 42

        result = await repo.count_documents()

        assert result == 42


class TestVersionCRUD:
    """Tests for DocumentVersion CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_version(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test version creation."""
        doc_uuid = uuid4()
        version = DocumentVersion(
            doc_uuid=doc_uuid,
            version_no=1,
            content_hash="abc123",
        )

        version_id = uuid4()
        now = datetime.now()
        mock_client.fetchrow.return_value = {
            "version_id": version_id,
            "created_at": now,
        }

        result = await repo.create_version(version)

        assert result.version_id == version_id
        assert result.doc_uuid == doc_uuid
        assert result.version_no == 1

    @pytest.mark.asyncio
    async def test_get_latest_version(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting latest version."""
        doc_uuid = uuid4()
        version_id = uuid4()
        mock_client.fetchrow.return_value = {
            "version_id": version_id,
            "doc_uuid": doc_uuid,
            "version_no": 3,
            "content_hash": "xyz789",
            "content_size": None,
            "effective_from": None,
            "effective_until": None,
            "approved_by": None,
            "approval_date": None,
            "change_summary": None,
            "created_at": datetime.now(),
        }

        result = await repo.get_latest_version(doc_uuid)

        assert result is not None
        assert result.version_no == 3

    @pytest.mark.asyncio
    async def test_get_latest_version_none(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting latest version when none exists."""
        mock_client.fetchrow.return_value = None

        result = await repo.get_latest_version(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_next_version_no(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting next version number."""
        mock_client.fetchval.return_value = 4

        result = await repo.get_next_version_no(uuid4())

        assert result == 4


class TestChunkCRUD:
    """Tests for Chunk CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_chunks(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating multiple chunks."""
        doc_uuid = uuid4()
        version_id = uuid4()
        chunks = [
            Chunk(doc_uuid=doc_uuid, version_id=version_id, chunk_no=1),
            Chunk(doc_uuid=doc_uuid, version_id=version_id, chunk_no=2),
        ]

        chunk_uuids = [uuid4(), uuid4()]
        now = datetime.now()

        # Mock transaction connection
        mock_conn = mock_client._mock_conn
        mock_conn.fetchrow.side_effect = [
            {"chunk_uuid": chunk_uuids[0], "created_at": now},
            {"chunk_uuid": chunk_uuids[1], "created_at": now},
        ]

        result = await repo.create_chunks(chunks)

        assert len(result) == 2
        assert result[0].chunk_uuid == chunk_uuids[0]
        assert result[1].chunk_uuid == chunk_uuids[1]

    @pytest.mark.asyncio
    async def test_create_chunks_empty_list(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating empty chunk list."""
        result = await repo.create_chunks([])

        assert result == []

    @pytest.mark.asyncio
    async def test_get_chunks_by_doc(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting chunks by document."""
        doc_uuid = uuid4()
        version_id = uuid4()
        chunk_uuid = uuid4()

        mock_client.fetch.return_value = [
            {
                "chunk_uuid": chunk_uuid,
                "doc_uuid": doc_uuid,
                "version_id": version_id,
                "chunk_no": 1,
                "section_path": "1.0",
                "chunk_text": "Test content",
                "char_start": None,
                "char_end": None,
                "token_count": None,
                "milvus_id": None,
                "neo4j_node_id": None,
                "embedding_model": None,
                "created_at": datetime.now(),
            }
        ]

        result = await repo.get_chunks_by_doc(doc_uuid)

        assert len(result) == 1
        assert result[0].chunk_uuid == chunk_uuid

    @pytest.mark.asyncio
    async def test_delete_chunks_by_doc(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting chunks by document."""
        mock_client.execute.return_value = "DELETE 5"

        result = await repo.delete_chunks_by_doc(uuid4())

        assert result == 5

    @pytest.mark.asyncio
    async def test_update_chunk_ids(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test updating chunk external IDs."""
        chunk_uuid = uuid4()

        await repo.update_chunk_ids(
            chunk_uuid, milvus_id="milvus123", neo4j_node_id="neo4j456"
        )

        mock_client.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_chunk_ids_empty(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test updating chunk with no IDs does nothing."""
        await repo.update_chunk_ids(uuid4())

        mock_client.execute.assert_not_called()


class TestACL:
    """Tests for ACL operations."""

    @pytest.mark.asyncio
    async def test_create_acl_entries(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating ACL entries."""
        doc_uuid = uuid4()
        entries = [
            AclEntry(
                doc_uuid=doc_uuid,
                principal_type="user",
                principal_id="user1",
                permission="read",
            ),
            AclEntry(
                doc_uuid=doc_uuid,
                principal_type="group",
                principal_id="group1",
                permission="write",
            ),
        ]

        await repo.create_acl_entries(entries)

        mock_conn = mock_client._mock_conn
        assert mock_conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_create_acl_entries_empty(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating empty ACL entry list."""
        await repo.create_acl_entries([])

        mock_client.transaction.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_accessible_doc_uuids(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting accessible documents."""
        doc_uuid = uuid4()
        mock_client.fetch.return_value = [{"doc_uuid": doc_uuid}]

        result = await repo.get_accessible_doc_uuids("user1", ["group1", "group2"])

        assert len(result) == 1
        assert result[0] == str(doc_uuid)

    @pytest.mark.asyncio
    async def test_check_access_granted(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test access check when granted."""
        mock_client.fetchrow.return_value = {"1": 1}

        result = await repo.check_access("user1", ["group1"], uuid4(), "read")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_access_denied(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test access check when denied."""
        mock_client.fetchrow.return_value = None

        result = await repo.check_access("user1", [], uuid4(), "read")

        assert result is False

    @pytest.mark.asyncio
    async def test_check_access_write_permission(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test access check for write permission."""
        mock_client.fetchrow.return_value = {"1": 1}

        result = await repo.check_access("user1", ["group1"], uuid4(), "write")

        assert result is True
        # Verify fetchrow was called
        mock_client.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_acl_entries(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting ACL entries."""
        mock_client.execute.return_value = "DELETE 3"

        result = await repo.delete_acl_entries(uuid4())

        assert result == 3


class TestAuditLog:
    """Tests for Audit Log operations."""

    @pytest.mark.asyncio
    async def test_create_audit_log(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating audit log."""
        log = AuditLog(
            user_id="user1",
            action="view",
            doc_uuid=uuid4(),
        )

        await repo.create_audit_log(log)

        mock_client.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_audit_log_with_retrieved_docs(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test creating audit log with retrieved docs."""
        log = AuditLog(
            user_id="user1",
            action="search",
            query_text="test query",
            retrieved_docs=[uuid4(), uuid4()],
            result_count=2,
        )

        await repo.create_audit_log(log)

        mock_client.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audit_logs(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting audit logs."""
        log_id = uuid4()
        mock_client.fetch.return_value = [
            {
                "log_id": log_id,
                "user_id": "user1",
                "user_org": "org1",
                "action": "view",
                "resource_type": "document",
                "doc_uuid": uuid4(),
                "query_text": None,
                "retrieved_docs": None,
                "result_count": None,
                "response_time_ms": None,
                "ip_address": None,
                "user_agent": None,
                "metadata": {},
                "timestamp": datetime.now(),
            }
        ]

        result = await repo.get_audit_logs(user_id="user1", limit=10)

        assert len(result) == 1
        assert result[0].log_id == log_id

    @pytest.mark.asyncio
    async def test_get_audit_logs_with_filters(
        self, repo: PostgresRepository, mock_client: MagicMock
    ) -> None:
        """Test getting audit logs with multiple filters."""
        mock_client.fetch.return_value = []

        result = await repo.get_audit_logs(
            user_id="user1",
            action="search",
            doc_uuid=uuid4(),
            limit=50,
        )

        assert result == []
        mock_client.fetch.assert_called_once()


class TestSingleton:
    """Tests for singleton factory."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_postgres_repository()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_postgres_repository()

    def test_get_postgres_repository_creates_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test get_postgres_repository creates instance."""
        repo = get_postgres_repository(mock_client)

        assert repo is not None
        assert isinstance(repo, PostgresRepository)

    def test_get_postgres_repository_returns_same_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test get_postgres_repository returns same instance."""
        repo1 = get_postgres_repository(mock_client)
        repo2 = get_postgres_repository(mock_client)

        assert repo1 is repo2
