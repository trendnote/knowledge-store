"""Integration test fixtures for search functionality.

This module provides fixtures for integration testing of the search service.
It can be configured to use either mock services or real infrastructure
via environment variables.

Usage:
    # Run with mocks (default)
    pytest tests/integration -v

    # Run with real infrastructure (requires Docker)
    INTEGRATION_TEST_REAL=1 pytest tests/integration -v
"""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio

from src.domain.search import SearchHit, SearchRequest, SearchResponse, SearchType
from src.services.search_service import SearchService


# =============================================================================
# Configuration
# =============================================================================


def use_real_infrastructure() -> bool:
    """Check if real infrastructure should be used."""
    return os.environ.get("INTEGRATION_TEST_REAL", "0") == "1"


# =============================================================================
# Test Data
# =============================================================================


TEST_DOCUMENTS = [
    {
        "doc_uuid": "doc-001",
        "title": "인공지능 기술 개요",
        "owner_id": "user1",
        "allowed_groups": ["engineering"],
        "chunks": [
            {
                "chunk_uuid": "chunk-001",
                "text": "인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.",
                "chunk_index": 0,
            },
            {
                "chunk_uuid": "chunk-002",
                "text": "머신러닝은 인공지능의 하위 분야로 데이터에서 학습합니다.",
                "chunk_index": 1,
            },
            {
                "chunk_uuid": "chunk-003",
                "text": "딥러닝은 신경망을 사용하는 머신러닝 기법입니다.",
                "chunk_index": 2,
            },
        ],
    },
    {
        "doc_uuid": "doc-002",
        "title": "자연어 처리 가이드",
        "owner_id": "user1",
        "allowed_groups": ["engineering", "ml-team"],
        "chunks": [
            {
                "chunk_uuid": "chunk-004",
                "text": "자연어 처리(NLP)는 텍스트와 음성을 이해하는 기술입니다.",
                "chunk_index": 0,
            },
            {
                "chunk_uuid": "chunk-005",
                "text": "토큰화는 텍스트를 작은 단위로 나누는 과정입니다.",
                "chunk_index": 1,
            },
        ],
    },
    {
        "doc_uuid": "doc-003",
        "title": "비공개 기밀 문서",
        "owner_id": "user2",
        "allowed_groups": [],
        "chunks": [
            {
                "chunk_uuid": "chunk-006",
                "text": "이 문서는 user2만 접근할 수 있는 비공개 기밀 정보입니다.",
                "chunk_index": 0,
            },
        ],
    },
    {
        "doc_uuid": "doc-004",
        "title": "전사 공개 문서",
        "owner_id": "admin",
        "allowed_groups": ["*"],  # Public
        "chunks": [
            {
                "chunk_uuid": "chunk-007",
                "text": "이 문서는 모든 사용자가 접근할 수 있는 공개 문서입니다.",
                "chunk_index": 0,
            },
            {
                "chunk_uuid": "chunk-008",
                "text": "회사 정책 및 가이드라인이 포함되어 있습니다.",
                "chunk_index": 1,
            },
        ],
    },
]


def get_test_documents() -> list[dict[str, Any]]:
    """Get test documents with unique UUIDs for each test run."""
    import copy

    docs = copy.deepcopy(TEST_DOCUMENTS)
    for doc in docs:
        doc["doc_uuid"] = str(uuid4())
        for chunk in doc["chunks"]:
            chunk["chunk_uuid"] = str(uuid4())
    return docs


# =============================================================================
# Mock Services
# =============================================================================


def create_mock_acl_service(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock ACL service that respects test data permissions."""
    service = MagicMock()

    async def get_accessible_documents(
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> list[str]:
        """Return accessible document UUIDs for user."""
        groups = user_groups or []
        accessible = []

        for doc in test_docs:
            # Owner has access
            if doc["owner_id"] == user_id:
                accessible.append(doc["doc_uuid"])
                continue

            # Check group access
            allowed_groups = doc.get("allowed_groups", [])
            if "*" in allowed_groups:
                accessible.append(doc["doc_uuid"])
                continue

            if any(g in allowed_groups for g in groups):
                accessible.append(doc["doc_uuid"])

        return accessible

    service.get_accessible_documents = AsyncMock(side_effect=get_accessible_documents)
    return service


def create_mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    service = MagicMock()

    def encode(texts: list[str]) -> MagicMock:
        result = MagicMock()
        # Generate deterministic mock embeddings based on text hash
        result.dense = [[0.1 * (hash(t) % 10) for _ in range(1024)] for t in texts]
        result.sparse = [{hash(t) % 1000: 0.5} for t in texts]
        return result

    service.encode = encode
    return service


def create_mock_milvus_repo(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock Milvus repository."""
    repo = MagicMock()

    # Build chunk index
    chunks_by_doc: dict[str, list[dict]] = {}
    all_chunks: list[dict] = []
    for doc in test_docs:
        chunks_by_doc[doc["doc_uuid"]] = doc["chunks"]
        for chunk in doc["chunks"]:
            all_chunks.append({**chunk, "doc_uuid": doc["doc_uuid"]})

    async def dense_search(
        query_vector: list[float],
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[SearchHit]:
        results = []
        for chunk in all_chunks:
            if doc_uuids and chunk["doc_uuid"] not in doc_uuids:
                continue
            results.append(
                SearchHit(
                    chunk_uuid=chunk["chunk_uuid"],
                    doc_uuid=chunk["doc_uuid"],
                    score=0.9 - len(results) * 0.05,
                    distance=0.1 + len(results) * 0.05,
                    chunk_text=chunk["text"],
                    search_type="dense",
                )
            )
            if len(results) >= top_k:
                break
        return results

    async def sparse_search(
        query_sparse: Any,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
        **kwargs: Any,
    ) -> list[SearchHit]:
        results = []
        for chunk in all_chunks:
            if doc_uuids and chunk["doc_uuid"] not in doc_uuids:
                continue
            results.append(
                SearchHit(
                    chunk_uuid=chunk["chunk_uuid"],
                    doc_uuid=chunk["doc_uuid"],
                    score=0.85 - len(results) * 0.05,
                    distance=0.15 + len(results) * 0.05,
                    chunk_text=chunk["text"],
                    search_type="sparse",
                )
            )
            if len(results) >= top_k:
                break
        return results

    repo.dense_search = AsyncMock(side_effect=dense_search)
    repo.sparse_search = AsyncMock(side_effect=sparse_search)
    return repo


def create_mock_neo4j_repo(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock Neo4j repository."""
    repo = MagicMock()

    # Build chunk index
    all_chunks: list[dict] = []
    for doc in test_docs:
        for chunk in doc["chunks"]:
            all_chunks.append({
                **chunk,
                "doc_uuid": doc["doc_uuid"],
                "title": doc["title"],
            })

    async def search_by_keyword(
        keyword: str,
        doc_uuids: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        results = []
        keyword_lower = keyword.lower()
        for chunk in all_chunks:
            if chunk["doc_uuid"] not in doc_uuids:
                continue
            if keyword_lower in chunk["text"].lower():
                results.append({
                    "chunk_uuid": chunk["chunk_uuid"],
                    "doc_uuid": chunk["doc_uuid"],
                    "text_preview": chunk["text"][:100],
                    "title": chunk["title"],
                    "path_length": 0,
                })
                if len(results) >= top_k:
                    break
        return results

    async def search_by_entity(
        entity_name: str,
        doc_uuids: list[str],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        return await search_by_keyword(entity_name, doc_uuids, top_k)

    repo.search_by_keyword = AsyncMock(side_effect=search_by_keyword)
    repo.search_by_entity = AsyncMock(side_effect=search_by_entity)
    return repo


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_docs() -> list[dict[str, Any]]:
    """Get test documents with unique UUIDs."""
    return get_test_documents()


@pytest.fixture(scope="function")
def mock_acl_service(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock ACL service."""
    return create_mock_acl_service(test_docs)


@pytest.fixture(scope="function")
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    return create_mock_embedding_service()


@pytest.fixture(scope="function")
def mock_milvus_repo(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock Milvus repository."""
    return create_mock_milvus_repo(test_docs)


@pytest.fixture(scope="function")
def mock_neo4j_repo(test_docs: list[dict[str, Any]]) -> MagicMock:
    """Create mock Neo4j repository."""
    return create_mock_neo4j_repo(test_docs)


@pytest_asyncio.fixture(scope="function")
async def search_service(
    mock_milvus_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_acl_service: MagicMock,
    mock_neo4j_repo: MagicMock,
) -> SearchService:
    """Create search service with mock dependencies."""
    return SearchService(
        milvus_repo=mock_milvus_repo,
        embedding_service=mock_embedding_service,
        acl_service=mock_acl_service,
        neo4j_repo=mock_neo4j_repo,
    )


@pytest.fixture(scope="function")
def test_data(test_docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Provide test data for tests."""
    return {
        "docs": test_docs,
        "user1_docs": [d for d in test_docs if d["owner_id"] == "user1"],
        "user2_docs": [d for d in test_docs if d["owner_id"] == "user2"],
        "public_docs": [d for d in test_docs if "*" in d.get("allowed_groups", [])],
    }
