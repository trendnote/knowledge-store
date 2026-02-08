"""E2E test fixtures and utilities.

This module provides fixtures for end-to-end testing of the Knowledge Store API.
Tests use httpx.AsyncClient for API interactions and include helpers for
document operations, search, and ACL testing.

Environment Setup:
    The tests can run against either:
    1. A locally running FastAPI server (set USE_TEST_CLIENT=false)
    2. A mock app with mocked services (default)

    Set API_BASE_URL environment variable to specify external server.
    Set USE_TEST_CLIENT=false to use external server.

Usage:
    pytest tests/e2e -m e2e -v  # Run E2E tests with mock app
    USE_TEST_CLIENT=false pytest tests/e2e -m e2e -v  # Run against real server
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

# Load environment variables from .env file
_env_file = Path(__file__).parent.parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)


# =============================================================================
# Event Loop Configuration
# =============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Mock Services
# =============================================================================


def create_mock_document_service() -> MagicMock:
    """Create a mock document service for E2E testing."""
    from dataclasses import dataclass
    from datetime import datetime

    service = MagicMock()

    # In-memory document storage
    documents: dict[str, dict] = {}

    @dataclass
    class MockDocumentResponse:
        doc_uuid: str
        title: str
        owner_id: str
        owner_org: str
        source: str
        status: str
        security_level: str
        chunk_count: int
        created_at: datetime
        updated_at: datetime
        source_url: str | None = None
        metadata: dict = None
        content: str = ""  # Extra for search

        def __post_init__(self):
            if self.metadata is None:
                self.metadata = {}

    async def create_document(request):
        """Create document - request contains owner_id, owner_org."""
        doc_uuid = str(uuid4())
        now = datetime.now()
        doc = {
            "doc_uuid": doc_uuid,
            "title": request.title,
            "content": request.content,
            "source": getattr(request, "source", "file"),
            "source_url": getattr(request, "source_url", None),
            "metadata": getattr(request, "metadata", {}),
            "owner_id": request.owner_id,
            "owner_org": getattr(request, "owner_org", "default"),
            "status": "published",
            "security_level": getattr(request, "security_level", "internal"),
            "chunk_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        documents[doc_uuid] = doc
        return MockDocumentResponse(**doc)

    async def get_document(doc_uuid, user_id, user_groups=None):
        """Get document with ACL check."""
        doc = documents.get(doc_uuid)
        if not doc:
            return None
        # Check ACL - owner or matching org
        if doc["owner_id"] != user_id:
            # Check org/group match
            if user_groups and doc["owner_org"] not in user_groups:
                return None
        return MockDocumentResponse(**doc)

    async def update_document(doc_uuid, request, user_id, user_groups=None):
        """Update document - only owner can update."""
        doc = documents.get(doc_uuid)
        if not doc:
            raise ValueError(f"Document {doc_uuid} not found")
        if doc["owner_id"] != user_id:
            raise PermissionError(f"User {user_id} cannot update document {doc_uuid}")

        if hasattr(request, "title") and request.title:
            doc["title"] = request.title
        if hasattr(request, "content") and request.content:
            doc["content"] = request.content
        doc["updated_at"] = datetime.now()
        return MockDocumentResponse(**doc)

    async def delete_document(doc_uuid, user_id, user_groups=None):
        """Delete document - only owner can delete."""
        doc = documents.get(doc_uuid)
        if not doc:
            raise ValueError(f"Document {doc_uuid} not found")
        if doc["owner_id"] != user_id:
            raise PermissionError(f"User {user_id} cannot delete document {doc_uuid}")
        del documents[doc_uuid]
        return True

    service.create_document = AsyncMock(side_effect=create_document)
    service.get_document = AsyncMock(side_effect=get_document)
    service.update_document = AsyncMock(side_effect=update_document)
    service.delete_document = AsyncMock(side_effect=delete_document)
    service._documents = documents  # Expose for search service

    return service


def create_mock_search_service(doc_service: MagicMock) -> MagicMock:
    """Create a mock search service for E2E testing."""
    from dataclasses import dataclass
    from src.domain.search import SearchType

    service = MagicMock()

    @dataclass
    class MockSearchHit:
        chunk_uuid: str
        doc_uuid: str
        score: float
        search_type: str
        chunk_text: str
        metadata: dict

    @dataclass
    class MockSearchResponse:
        results: list
        total: int
        search_types_used: list
        search_time_ms: float = 10.0

    async def unified_search(request):
        user_id = request.user_id
        user_groups = request.user_groups or []
        query = request.query.lower()
        top_k = getattr(request, "top_k", 10)

        # Search through documents
        results = []
        for doc_uuid, doc in doc_service._documents.items():
            # ACL check - user must be owner or in same org/group
            doc_owner_org = doc.get("owner_org", "default")
            if doc["owner_id"] != user_id and doc_owner_org not in user_groups:
                continue

            # Simple text matching
            content = (doc.get("content", "") + " " + doc.get("title", "")).lower()
            if query in content or any(word in content for word in query.split()):
                results.append(MockSearchHit(
                    chunk_uuid=str(uuid4()),
                    doc_uuid=doc_uuid,
                    score=0.9,
                    search_type="dense",
                    chunk_text=doc.get("content", "")[:500] if doc.get("content") else "",
                    metadata={"title": doc["title"]},
                ))

        return MockSearchResponse(
            results=results[:top_k],
            total=len(results),
            search_types_used=[SearchType.DENSE],
        )

    service.unified_search = AsyncMock(side_effect=unified_search)
    return service


# =============================================================================
# API Client Configuration
# =============================================================================


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Get API base URL from environment or use default."""
    return os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def use_test_client() -> bool:
    """Determine whether to use mock app or external server."""
    return os.environ.get("USE_TEST_CLIENT", "true").lower() == "true"


@pytest_asyncio.fixture(scope="function")
async def api_client(
    api_base_url: str,
    use_test_client: bool,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Create async HTTP client for API testing.

    Uses httpx.ASGITransport for testing against the mock app,
    or connects to an external server.
    """
    import httpx

    if use_test_client:
        # Create mock services
        mock_doc_service = create_mock_document_service()
        mock_search_service = create_mock_search_service(mock_doc_service)

        # Patch dependencies for lifespan
        with (
            patch("src.api.dependencies.init_clients", new_callable=AsyncMock),
            patch("src.api.dependencies.init_services", new_callable=AsyncMock),
            patch("src.api.dependencies.close_clients", new_callable=AsyncMock),
            patch("src.api.routers.health.set_clients"),
            patch(
                "src.api.dependencies.get_clients_for_health",
                return_value={
                    "postgres": None,
                    "milvus": None,
                    "neo4j": None,
                    "kafka": None,
                },
            ),
        ):
            from src.api.routers import documents as documents_router
            from src.api.routers import search as search_router
            from src.main import create_app

            app = create_app()

            # Override router dependencies
            async def get_mock_doc_service():
                return mock_doc_service

            async def get_mock_search_service():
                return mock_search_service

            app.dependency_overrides[documents_router.get_document_service] = (
                get_mock_doc_service
            )
            app.dependency_overrides[search_router.get_search_service] = (
                get_mock_search_service
            )

            # Use ASGITransport for async testing
            transport = httpx.ASGITransport(app=app)  # type: ignore

            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                timeout=30.0,
            ) as client:
                yield client

            # Clear overrides
            app.dependency_overrides.clear()
    else:
        # Use real async client for external server
        async with httpx.AsyncClient(
            base_url=api_base_url,
            timeout=30.0,
        ) as client:
            # Check if server is available
            try:
                response = await client.get("/health")
                if response.status_code != 200:
                    pytest.skip(f"Server not healthy at {api_base_url}")
            except Exception as e:
                pytest.skip(f"Cannot connect to server at {api_base_url}: {e}")

            yield client


# =============================================================================
# User Headers Fixtures
# =============================================================================


@pytest.fixture
def user1_headers() -> dict[str, str]:
    """Headers for test user1 (engineering team member)."""
    return {
        "X-User-Id": "user1",
        "X-User-Org": "engineering",
        "X-User-Groups": "engineering,ml-team",
        "Content-Type": "application/json",
    }


@pytest.fixture
def user2_headers() -> dict[str, str]:
    """Headers for test user2 (marketing team member)."""
    return {
        "X-User-Id": "user2",
        "X-User-Org": "marketing",
        "X-User-Groups": "marketing",
        "Content-Type": "application/json",
    }


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Headers for admin user."""
    return {
        "X-User-Id": "admin",
        "X-User-Org": "admin",
        "X-User-Groups": "admin,engineering",
        "Content-Type": "application/json",
    }


@pytest.fixture
def public_headers() -> dict[str, str]:
    """Headers for public/anonymous access."""
    return {
        "X-User-Id": "anonymous",
        "X-User-Org": "public",
        "X-User-Groups": "public",
        "Content-Type": "application/json",
    }


# =============================================================================
# Document Helper Class
# =============================================================================


class DocumentHelper:
    """Helper class for document operations in E2E tests."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
    ) -> None:
        import httpx
        self.client: httpx.AsyncClient = client
        self.headers = headers
        self.created_docs: list[str] = []

    async def create(
        self,
        title: str,
        content: str,
        source: str = "file",
        metadata: dict | None = None,
        **kwargs,
    ) -> dict:
        """Create a document."""
        body = {
            "title": title,
            "content": content,
            "source": source,
            "metadata": metadata or {},
            **kwargs,
        }

        response = await self.client.post(
            "/api/v1/documents",
            json=body,
            headers=self.headers,
        )
        response.raise_for_status()

        data = response.json()
        doc_uuid = data.get("doc_uuid") or data.get("id")
        if doc_uuid:
            self.created_docs.append(doc_uuid)

        return data

    async def get(self, doc_uuid: str) -> dict | None:
        """Get a document by UUID."""
        response = await self.client.get(
            f"/api/v1/documents/{doc_uuid}",
            headers=self.headers,
        )

        if response.status_code in [404, 403]:
            return None

        response.raise_for_status()
        return response.json()

    async def update(
        self,
        doc_uuid: str,
        title: str | None = None,
        content: str | None = None,
        **kwargs,
    ) -> dict:
        """Update a document."""
        body = {}
        if title is not None:
            body["title"] = title
        if content is not None:
            body["content"] = content
        body.update(kwargs)

        response = await self.client.put(
            f"/api/v1/documents/{doc_uuid}",
            json=body,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def delete(self, doc_uuid: str) -> bool:
        """Delete a document."""
        response = await self.client.delete(
            f"/api/v1/documents/{doc_uuid}",
            headers=self.headers,
        )

        if response.status_code in [200, 204]:
            if doc_uuid in self.created_docs:
                self.created_docs.remove(doc_uuid)
            return True

        return False

    async def search(
        self,
        query: str,
        top_k: int = 10,
        search_types: list[str] | None = None,
        filters: dict | None = None,
    ) -> dict:
        """Search documents."""
        user_id = self.headers.get("X-User-Id", "anonymous")
        user_groups_str = self.headers.get("X-User-Groups", "")
        user_groups = [g.strip() for g in user_groups_str.split(",") if g.strip()]

        body: dict = {
            "query": query,
            "user_id": user_id,
            "user_groups": user_groups,
            "top_k": top_k,
        }

        if search_types:
            body["search_types"] = search_types

        if filters:
            body["filters"] = filters

        response = await self.client.post(
            "/api/v1/search",
            json=body,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()

    async def wait_for_indexing(self, seconds: float = 0.1) -> None:
        """Wait for document indexing (reduced for mock tests)."""
        await asyncio.sleep(seconds)

    async def wait_for_sync(self, seconds: float = 0.1) -> None:
        """Wait for sync (reduced for mock tests)."""
        await asyncio.sleep(seconds)

    async def cleanup(self) -> None:
        """Clean up all created documents."""
        for doc_uuid in list(self.created_docs):
            try:
                await self.delete(doc_uuid)
            except Exception:
                pass
        self.created_docs.clear()


# =============================================================================
# Document Helper Fixtures
# =============================================================================


@pytest_asyncio.fixture
async def doc_helper(
    api_client: httpx.AsyncClient,
    user1_headers: dict[str, str],
) -> AsyncGenerator[DocumentHelper, None]:
    """Create document helper for user1."""
    helper = DocumentHelper(api_client, user1_headers)
    yield helper
    await helper.cleanup()


@pytest_asyncio.fixture
async def doc_helper_user2(
    api_client: httpx.AsyncClient,
    user2_headers: dict[str, str],
) -> AsyncGenerator[DocumentHelper, None]:
    """Create document helper for user2."""
    helper = DocumentHelper(api_client, user2_headers)
    yield helper
    await helper.cleanup()


@pytest_asyncio.fixture
async def doc_helper_admin(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> AsyncGenerator[DocumentHelper, None]:
    """Create document helper for admin."""
    helper = DocumentHelper(api_client, admin_headers)
    yield helper
    await helper.cleanup()


# =============================================================================
# Performance Measurement Utilities
# =============================================================================


class Timer:
    """Context manager for timing operations."""

    def __init__(self) -> None:
        self.start_time: float = 0
        self.end_time: float = 0

    def __enter__(self) -> Timer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        self.end_time = time.perf_counter()

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds."""
        return self.end_time - self.start_time

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self.elapsed * 1000


@pytest.fixture
def timer() -> type[Timer]:
    """Provide Timer class for performance measurements."""
    return Timer


# =============================================================================
# Test Data Generators
# =============================================================================


@pytest.fixture
def unique_id() -> str:
    """Generate a unique ID for test isolation."""
    return str(uuid4())[:8]


@pytest.fixture
def sample_documents() -> list[dict[str, str]]:
    """Sample documents for testing."""
    return [
        {
            "title": "인공지능 기술 개요",
            "content": "인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.",
        },
        {
            "title": "데이터베이스 설계 원칙",
            "content": "데이터베이스 설계에서 정규화는 중요한 개념입니다.",
        },
        {
            "title": "API 설계 모범 사례",
            "content": "RESTful API는 HTTP 메서드를 활용합니다.",
        },
    ]
