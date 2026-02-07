"""Tests for document API router."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.documents import router


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_document_response() -> MagicMock:
    """Create mock document response."""
    response = MagicMock()
    response.doc_uuid = "doc-123"
    response.title = "Test Document"
    response.owner_id = "user1"
    response.owner_org = "engineering"
    response.source = "file"
    response.source_url = "https://example.com/doc.pdf"
    response.status = "draft"
    response.security_level = "internal"
    response.chunk_count = 5
    response.created_at = datetime.utcnow()
    response.updated_at = datetime.utcnow()
    response.metadata = {"key": "value"}
    return response


@pytest.fixture
def mock_document_service(mock_document_response: MagicMock) -> MagicMock:
    """Create mock document service."""
    service = MagicMock()
    service.create_document = AsyncMock(return_value=mock_document_response)
    service.get_document = AsyncMock(return_value=mock_document_response)
    service.list_documents = AsyncMock(return_value=[mock_document_response])
    service.update_document = AsyncMock(return_value=mock_document_response)
    service.delete_document = AsyncMock(return_value=True)
    return service


@pytest.fixture
def client(mock_document_service: MagicMock) -> TestClient:
    """Create test client with mocked service."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def get_mock_service() -> Any:
        return mock_document_service

    from src.api.routers import documents
    app.dependency_overrides[documents.get_document_service] = get_mock_service

    return TestClient(app)


# =============================================================================
# Test Create Document
# =============================================================================


class TestCreateDocument:
    """Tests for POST /documents endpoint."""

    def test_create_document_success(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test successful document creation."""
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Test Document",
                "content": "This is test content for the document.",
            },
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["doc_uuid"] == "doc-123"
        assert data["title"] == "Test Document"
        assert data["owner_id"] == "user1"
        mock_document_service.create_document.assert_called_once()

    def test_create_document_with_all_fields(
        self,
        client: TestClient,
    ) -> None:
        """Test creation with all optional fields."""
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Full Document",
                "content": "Content here",
                "source": "confluence",
                "source_url": "https://example.com/doc",
                "security_level": "confidential",
                "metadata": {"department": "engineering"},
                "chunk_size": 800,
                "chunk_overlap": 100,
            },
            headers={"x-user-id": "user1", "x-user-org": "acme"},
        )

        assert response.status_code == 201

    def test_create_document_missing_user_id(
        self,
        client: TestClient,
    ) -> None:
        """Test creation without user ID header fails."""
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Test",
                "content": "Content",
            },
        )

        assert response.status_code == 422

    def test_create_document_empty_title(
        self,
        client: TestClient,
    ) -> None:
        """Test creation with empty title fails."""
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "   ",
                "content": "Content",
            },
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 422

    def test_create_document_empty_content(
        self,
        client: TestClient,
    ) -> None:
        """Test creation with empty content fails."""
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Title",
                "content": "",
            },
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 422

    def test_create_document_service_error(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test creation handles service errors."""
        mock_document_service.create_document = AsyncMock(
            side_effect=ValueError("Invalid content")
        )

        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Test",
                "content": "Content",
            },
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 400
        assert "Invalid content" in response.json()["detail"]


# =============================================================================
# Test Get Document
# =============================================================================


class TestGetDocument:
    """Tests for GET /documents/{doc_uuid} endpoint."""

    def test_get_document_success(
        self,
        client: TestClient,
    ) -> None:
        """Test successful document retrieval."""
        response = client.get(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["doc_uuid"] == "doc-123"
        assert data["title"] == "Test Document"

    def test_get_document_with_groups(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test retrieval with user groups."""
        response = client.get(
            "/api/v1/documents/doc-123",
            headers={
                "x-user-id": "user1",
                "x-user-groups": "engineering,ml-team",
            },
        )

        assert response.status_code == 200
        # Verify groups were passed to service
        call_args = mock_document_service.get_document.call_args
        assert "engineering" in call_args.kwargs.get("user_groups", [])

    def test_get_document_not_found(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test retrieval of non-existent document."""
        mock_document_service.get_document = AsyncMock(return_value=None)

        response = client.get(
            "/api/v1/documents/nonexistent",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_document_access_denied(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test retrieval with access denied."""
        mock_document_service.get_document = AsyncMock(
            side_effect=PermissionError("Access denied")
        )

        response = client.get(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]


# =============================================================================
# Test List Documents
# =============================================================================


class TestListDocuments:
    """Tests for GET /documents endpoint."""

    def test_list_documents_success(
        self,
        client: TestClient,
    ) -> None:
        """Test successful document listing."""
        response = client.get(
            "/api/v1/documents",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert len(data["documents"]) == 1
        assert data["total"] == 1
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_list_documents_with_pagination(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test listing with pagination parameters."""
        response = client.get(
            "/api/v1/documents",
            params={"limit": 10, "offset": 5},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 5

    def test_list_documents_with_status_filter(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test listing with status filter."""
        response = client.get(
            "/api/v1/documents",
            params={"status": "published"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200
        call_args = mock_document_service.list_documents.call_args
        assert call_args.kwargs.get("status") == "published"

    def test_list_documents_with_groups(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test listing with user groups."""
        response = client.get(
            "/api/v1/documents",
            headers={
                "x-user-id": "user1",
                "x-user-groups": "engineering, ml-team",
            },
        )

        assert response.status_code == 200
        call_args = mock_document_service.list_documents.call_args
        groups = call_args.kwargs.get("user_groups", [])
        assert "engineering" in groups
        assert "ml-team" in groups


# =============================================================================
# Test Update Document
# =============================================================================


class TestUpdateDocument:
    """Tests for PUT /documents/{doc_uuid} endpoint."""

    def test_update_document_title(
        self,
        client: TestClient,
    ) -> None:
        """Test updating document title."""
        response = client.put(
            "/api/v1/documents/doc-123",
            json={"title": "Updated Title"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200

    def test_update_document_content(
        self,
        client: TestClient,
    ) -> None:
        """Test updating document content."""
        response = client.put(
            "/api/v1/documents/doc-123",
            json={"content": "New content here"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200

    def test_update_document_status(
        self,
        client: TestClient,
    ) -> None:
        """Test updating document status."""
        response = client.put(
            "/api/v1/documents/doc-123",
            json={"status": "published"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 200

    def test_update_document_not_found(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test updating non-existent document."""
        mock_document_service.update_document = AsyncMock(
            side_effect=ValueError("Document not found: doc-123")
        )

        response = client.put(
            "/api/v1/documents/doc-123",
            json={"title": "New Title"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 404

    def test_update_document_access_denied(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test updating without permission."""
        mock_document_service.update_document = AsyncMock(
            side_effect=PermissionError("Access denied")
        )

        response = client.put(
            "/api/v1/documents/doc-123",
            json={"title": "New Title"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 403


# =============================================================================
# Test Delete Document
# =============================================================================


class TestDeleteDocument:
    """Tests for DELETE /documents/{doc_uuid} endpoint."""

    def test_delete_document_success(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test successful document deletion."""
        response = client.delete(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 204
        mock_document_service.delete_document.assert_called_once()

    def test_delete_document_with_groups(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test deletion with user groups."""
        response = client.delete(
            "/api/v1/documents/doc-123",
            headers={
                "x-user-id": "user1",
                "x-user-groups": "admin",
            },
        )

        assert response.status_code == 204

    def test_delete_document_not_found(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test deleting non-existent document."""
        mock_document_service.delete_document = AsyncMock(
            side_effect=ValueError("Document not found: doc-123")
        )

        response = client.delete(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 404

    def test_delete_document_access_denied(
        self,
        client: TestClient,
        mock_document_service: MagicMock,
    ) -> None:
        """Test deleting without permission."""
        mock_document_service.delete_document = AsyncMock(
            side_effect=PermissionError("Access denied")
        )

        response = client.delete(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 403


# =============================================================================
# Test Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Tests for router helper functions."""

    def test_parse_user_groups_empty(self) -> None:
        """Test parsing empty groups header."""
        from src.api.routers.documents import _parse_user_groups

        assert _parse_user_groups(None) == []
        assert _parse_user_groups("") == []

    def test_parse_user_groups_single(self) -> None:
        """Test parsing single group."""
        from src.api.routers.documents import _parse_user_groups

        assert _parse_user_groups("engineering") == ["engineering"]

    def test_parse_user_groups_multiple(self) -> None:
        """Test parsing multiple groups."""
        from src.api.routers.documents import _parse_user_groups

        result = _parse_user_groups("engineering, ml-team, admin")
        assert "engineering" in result
        assert "ml-team" in result
        assert "admin" in result

    def test_parse_user_groups_strips_whitespace(self) -> None:
        """Test parsing strips whitespace."""
        from src.api.routers.documents import _parse_user_groups

        result = _parse_user_groups("  engineering  ,  ml-team  ")
        assert result == ["engineering", "ml-team"]
