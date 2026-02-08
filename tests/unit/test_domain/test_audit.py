"""Tests for audit domain models."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.audit import (
    AuditAction,
    AuditLogEntry,
    AuditQuery,
    ResourceType,
)


# =============================================================================
# Test AuditAction Enum
# =============================================================================


class TestAuditAction:
    """Tests for AuditAction enum."""

    def test_search_actions(self) -> None:
        """Test search action values."""
        assert AuditAction.SEARCH.value == "search"
        assert AuditAction.SEARCH_DENSE.value == "search_dense"
        assert AuditAction.SEARCH_SPARSE.value == "search_sparse"
        assert AuditAction.SEARCH_GRAPH.value == "search_graph"
        assert AuditAction.SEARCH_HYBRID.value == "search_hybrid"

    def test_document_actions(self) -> None:
        """Test document action values."""
        assert AuditAction.DOCUMENT_CREATE.value == "document_create"
        assert AuditAction.DOCUMENT_READ.value == "document_read"
        assert AuditAction.DOCUMENT_UPDATE.value == "document_update"
        assert AuditAction.DOCUMENT_DELETE.value == "document_delete"
        assert AuditAction.DOCUMENT_LIST.value == "document_list"

    def test_permission_actions(self) -> None:
        """Test permission action values."""
        assert AuditAction.PERMISSION_GRANT.value == "permission_grant"
        assert AuditAction.PERMISSION_REVOKE.value == "permission_revoke"
        assert AuditAction.PERMISSION_CHECK.value == "permission_check"

    def test_other_actions(self) -> None:
        """Test other action values."""
        assert AuditAction.EXPORT.value == "export"
        assert AuditAction.SHARE.value == "share"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert AuditAction("search") == AuditAction.SEARCH
        assert AuditAction("document_create") == AuditAction.DOCUMENT_CREATE


# =============================================================================
# Test ResourceType Enum
# =============================================================================


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_resource_type_values(self) -> None:
        """Test resource type values."""
        assert ResourceType.DOCUMENT.value == "document"
        assert ResourceType.CHUNK.value == "chunk"
        assert ResourceType.SEARCH.value == "search"
        assert ResourceType.PERMISSION.value == "permission"
        assert ResourceType.ACL.value == "acl"
        assert ResourceType.SYSTEM.value == "system"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert ResourceType("document") == ResourceType.DOCUMENT
        assert ResourceType("search") == ResourceType.SEARCH


# =============================================================================
# Test AuditLogEntry
# =============================================================================


class TestAuditLogEntry:
    """Tests for AuditLogEntry model."""

    def test_create_minimal_entry(self) -> None:
        """Test creating entry with minimal fields."""
        entry = AuditLogEntry(
            user_id="user1",
            action=AuditAction.SEARCH,
            resource_type=ResourceType.SEARCH,
        )

        assert entry.user_id == "user1"
        assert entry.action == AuditAction.SEARCH
        assert entry.resource_type == ResourceType.SEARCH
        assert entry.resource_id is None
        assert entry.query_text is None
        assert entry.retrieved_docs == []
        assert entry.metadata == {}
        assert entry.ip_address is None
        assert entry.user_agent is None
        assert isinstance(entry.created_at, datetime)
        assert entry.id is None

    def test_create_full_entry(self) -> None:
        """Test creating entry with all fields."""
        now = datetime.utcnow()
        entry = AuditLogEntry(
            user_id="user1",
            action=AuditAction.SEARCH_HYBRID,
            resource_type=ResourceType.SEARCH,
            resource_id="query-123",
            query_text="test query",
            retrieved_docs=["doc1", "doc2"],
            metadata={"duration_ms": 150},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            created_at=now,
            id=42,
        )

        assert entry.user_id == "user1"
        assert entry.action == AuditAction.SEARCH_HYBRID
        assert entry.resource_type == ResourceType.SEARCH
        assert entry.resource_id == "query-123"
        assert entry.query_text == "test query"
        assert entry.retrieved_docs == ["doc1", "doc2"]
        assert entry.metadata == {"duration_ms": 150}
        assert entry.ip_address == "192.168.1.1"
        assert entry.user_agent == "Mozilla/5.0"
        assert entry.created_at == now
        assert entry.id == 42

    def test_to_dict(self) -> None:
        """Test converting entry to dictionary."""
        entry = AuditLogEntry(
            user_id="user1",
            action=AuditAction.DOCUMENT_READ,
            resource_type=ResourceType.DOCUMENT,
            resource_id="doc-123",
            metadata={"key": "value"},
        )

        data = entry.to_dict()

        assert data["user_id"] == "user1"
        assert data["action"] == "document_read"
        assert data["resource_type"] == "document"
        assert data["resource_id"] == "doc-123"
        assert data["metadata"] == {"key": "value"}
        assert "created_at" in data

    def test_from_dict(self) -> None:
        """Test creating entry from dictionary."""
        data = {
            "user_id": "user1",
            "action": "search_hybrid",
            "resource_type": "search",
            "query_text": "test query",
            "retrieved_docs": ["doc1"],
            "metadata": {"result_count": 10},
            "ip_address": "10.0.0.1",
            "created_at": "2026-01-26T10:00:00",
        }

        entry = AuditLogEntry.from_dict(data)

        assert entry.user_id == "user1"
        assert entry.action == AuditAction.SEARCH_HYBRID
        assert entry.resource_type == ResourceType.SEARCH
        assert entry.query_text == "test query"
        assert entry.retrieved_docs == ["doc1"]
        assert entry.metadata == {"result_count": 10}
        assert entry.ip_address == "10.0.0.1"

    def test_from_dict_with_z_timestamp(self) -> None:
        """Test parsing timestamp with Z suffix."""
        data = {
            "user_id": "user1",
            "action": "search",
            "resource_type": "search",
            "created_at": "2026-01-26T10:00:00Z",
        }

        entry = AuditLogEntry.from_dict(data)

        assert entry.created_at.year == 2026
        assert entry.created_at.month == 1

    def test_from_dict_without_timestamp(self) -> None:
        """Test parsing without timestamp uses current time."""
        data = {
            "user_id": "user1",
            "action": "search",
            "resource_type": "search",
        }

        before = datetime.utcnow()
        entry = AuditLogEntry.from_dict(data)
        after = datetime.utcnow()

        assert before <= entry.created_at <= after


# =============================================================================
# Test AuditQuery
# =============================================================================


class TestAuditQuery:
    """Tests for AuditQuery model."""

    def test_create_empty_query(self) -> None:
        """Test creating empty query."""
        query = AuditQuery()

        assert query.user_id is None
        assert query.action is None
        assert query.resource_type is None
        assert query.resource_id is None
        assert query.start_time is None
        assert query.end_time is None
        assert query.limit == 100
        assert query.offset == 0

    def test_create_full_query(self) -> None:
        """Test creating query with all filters."""
        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)

        query = AuditQuery(
            user_id="user1",
            action=AuditAction.SEARCH,
            resource_type=ResourceType.SEARCH,
            resource_id="res-123",
            start_time=start,
            end_time=end,
            limit=50,
            offset=10,
        )

        assert query.user_id == "user1"
        assert query.action == AuditAction.SEARCH
        assert query.resource_type == ResourceType.SEARCH
        assert query.resource_id == "res-123"
        assert query.start_time == start
        assert query.end_time == end
        assert query.limit == 50
        assert query.offset == 10

    def test_to_dict_empty_query(self) -> None:
        """Test converting empty query to dict."""
        query = AuditQuery()
        data = query.to_dict()

        assert "user_id" not in data
        assert "action" not in data
        assert data["limit"] == 100
        assert data["offset"] == 0

    def test_to_dict_full_query(self) -> None:
        """Test converting full query to dict."""
        query = AuditQuery(
            user_id="user1",
            action=AuditAction.DOCUMENT_READ,
            resource_type=ResourceType.DOCUMENT,
        )
        data = query.to_dict()

        assert data["user_id"] == "user1"
        assert data["action"] == "document_read"
        assert data["resource_type"] == "document"
