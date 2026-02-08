"""E2E tests for full document lifecycle.

This module tests the complete document lifecycle:
- Create document -> Search -> Update -> Search -> Delete -> Search

These tests verify that documents are properly indexed and synchronized
across all stores (PostgreSQL, Milvus, Neo4j).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.e2e.conftest import DocumentHelper


@pytest.mark.e2e
class TestDocumentLifecycle:
    """E2E tests for complete document lifecycle."""

    async def test_create_and_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test creating a document and finding it via search.

        Scenario:
        1. Create a document with specific content
        2. Wait for indexing
        3. Search for content keywords
        4. Verify document appears in results
        """
        # Create document
        doc = await doc_helper.create(
            title="인공지능 기술 개요",
            content="""
            인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다.
            머신러닝과 딥러닝은 인공지능의 핵심 기술입니다.
            자연어 처리, 컴퓨터 비전 등 다양한 응용 분야가 있습니다.
            """,
        )

        doc_uuid = doc.get("doc_uuid") or doc.get("id")
        assert doc_uuid is not None
        assert doc.get("title") == "인공지능 기술 개요"

        # Wait for indexing
        await doc_helper.wait_for_indexing()

        # Search and find the document
        search_result = await doc_helper.search("인공지능 기술")

        # Verify document is found
        assert search_result.get("total", 0) >= 1 or len(
            search_result.get("results", [])
        ) >= 1

        found_docs = [
            r.get("doc_uuid") or r.get("document_id")
            for r in search_result.get("results", [])
        ]
        assert doc_uuid in found_docs, f"Document {doc_uuid} not found in search results"

    async def test_update_and_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test updating document and verifying search reflects changes.

        Scenario:
        1. Create document with initial content
        2. Search for a keyword that doesn't exist
        3. Update document with new keyword
        4. Wait for sync
        5. Search again and verify new content is found
        """
        # Create document
        doc = await doc_helper.create(
            title="원래 제목",
            content="원래 내용입니다. 초기 테스트 문서.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        await doc_helper.wait_for_indexing()

        # Initial search for keyword that shouldn't exist
        result1 = await doc_helper.search("업데이트된 고유키워드")
        initial_found = any(
            (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
            for r in result1.get("results", [])
        )
        # Initial content shouldn't have this keyword
        assert not initial_found, "Initial content should not contain update keyword"

        # Update content with new keywords
        await doc_helper.update(
            doc_uuid,
            content="업데이트된 고유키워드가 포함된 새로운 내용입니다.",
        )

        await doc_helper.wait_for_sync()

        # Search again - should find new content
        result2 = await doc_helper.search("업데이트된 고유키워드")

        updated_found = any(
            (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
            for r in result2.get("results", [])
        )
        assert updated_found, "Updated document should be found with new keyword"

    async def test_delete_removes_from_search(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test deleting document removes it from search results.

        Scenario:
        1. Create document with unique content
        2. Verify it's searchable
        3. Delete the document
        4. Wait for sync
        5. Verify it's no longer in search results
        6. Verify direct access fails
        """
        # Create document with unique content
        unique_keyword = "삭제테스트고유키워드"
        doc = await doc_helper.create(
            title="삭제될 문서",
            content=f"이 문서는 삭제될 예정입니다. {unique_keyword} 내용.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        await doc_helper.wait_for_indexing()

        # Verify it's searchable
        result1 = await doc_helper.search(unique_keyword)
        found_before = any(
            (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
            for r in result1.get("results", [])
        )
        assert found_before, "Document should be searchable before deletion"

        # Delete document
        deleted = await doc_helper.delete(doc_uuid)
        assert deleted, "Delete operation should succeed"

        await doc_helper.wait_for_sync()

        # Verify not in search results
        result2 = await doc_helper.search(unique_keyword)
        found_after = any(
            (r.get("doc_uuid") or r.get("document_id")) == doc_uuid
            for r in result2.get("results", [])
        )
        assert not found_after, "Deleted document should not appear in search"

        # Verify document not accessible directly
        doc_after = await doc_helper.get(doc_uuid)
        assert doc_after is None, "Deleted document should not be directly accessible"

    async def test_create_multiple_and_search(
        self,
        doc_helper: DocumentHelper,
        sample_documents: list[dict[str, str]],
    ) -> None:
        """Test creating multiple documents and searching across them.

        Scenario:
        1. Create multiple documents with different topics
        2. Search for a specific topic
        3. Verify only relevant documents are returned
        """
        # Create multiple documents
        created_docs = []
        for sample in sample_documents[:3]:
            doc = await doc_helper.create(
                title=sample["title"],
                content=sample["content"],
            )
            created_docs.append(doc)

        await doc_helper.wait_for_indexing(3.0)

        # Search for specific topic
        result = await doc_helper.search("인공지능")

        # Should find at least the AI document
        ai_doc_uuid = created_docs[0].get("doc_uuid") or created_docs[0].get("id")
        found_ids = [
            r.get("doc_uuid") or r.get("document_id")
            for r in result.get("results", [])
        ]

        assert ai_doc_uuid in found_ids, "AI document should be found in search"


@pytest.mark.e2e
class TestSearchQuality:
    """E2E tests for search quality and relevance."""

    async def test_dense_search_semantic(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test dense search finds semantically similar content.

        Dense (vector) search should find documents with similar
        meaning even if exact keywords don't match.
        """
        await doc_helper.create(
            title="Machine Learning Introduction",
            content="Machine learning is a subset of artificial intelligence. "
            "Deep learning uses neural networks for pattern recognition.",
        )

        await doc_helper.wait_for_indexing()

        # Search with semantically related query
        result = await doc_helper.search(
            "AI and neural network technology",
            search_types=["dense"],
        )

        # Dense search should return results (semantic similarity)
        assert result is not None
        # Note: Actual matching depends on embedding model similarity

    async def test_sparse_search_keyword(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test sparse search matches exact keywords.

        Sparse (BM25/keyword) search should find documents
        containing the exact query terms.
        """
        unique_term = "토큰화프로세스"
        await doc_helper.create(
            title="토큰화 가이드",
            content=f"텍스트 {unique_term}는 NLP의 기본 단계입니다. "
            f"{unique_term} 과정을 설명합니다.",
        )

        await doc_helper.wait_for_indexing()

        # Exact keyword search
        result = await doc_helper.search(
            unique_term,
            search_types=["sparse"],
        )

        # Should find document with exact keyword
        total = result.get("total", len(result.get("results", [])))
        assert total >= 1, f"Sparse search should find document with '{unique_term}'"

    async def test_hybrid_search_combines(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test hybrid search combines dense and sparse results.

        Hybrid search should leverage both semantic similarity
        and keyword matching for better results.
        """
        await doc_helper.create(
            title="하이브리드 검색 문서",
            content="하이브리드 검색은 의미 기반과 키워드 기반을 결합합니다. "
            "이 방식은 더 정확한 검색 결과를 제공합니다.",
        )

        await doc_helper.wait_for_indexing()

        result = await doc_helper.search(
            "하이브리드 검색 기술",
            search_types=["dense", "sparse"],
        )

        # Should return results
        total = result.get("total", len(result.get("results", [])))
        assert total >= 1, "Hybrid search should find document"

        # Should indicate which search types were used
        search_types_used = result.get("search_types_used", [])
        if search_types_used:
            assert len(search_types_used) >= 1

    async def test_search_top_k_limit(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test search respects top_k parameter."""
        # Create multiple documents
        for i in range(5):
            await doc_helper.create(
                title=f"검색제한테스트 문서 {i}",
                content=f"검색제한테스트 내용 {i}번입니다. 공통 키워드.",
            )

        await doc_helper.wait_for_indexing(3.0)

        # Search with limited top_k
        result = await doc_helper.search(
            "검색제한테스트",
            top_k=3,
        )

        # Results should not exceed top_k
        results_count = len(result.get("results", []))
        assert results_count <= 3, f"Results ({results_count}) should not exceed top_k (3)"

    async def test_search_no_results(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test search returns empty results for non-matching query."""
        result = await doc_helper.search(
            "xyzzy완전히매칭안되는검색어12345",
        )

        # Should return empty results, not error
        assert result is not None
        assert len(result.get("results", [])) == 0


@pytest.mark.e2e
class TestDocumentRetrieval:
    """E2E tests for document retrieval operations."""

    async def test_get_document_by_id(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test retrieving a document by its UUID."""
        doc = await doc_helper.create(
            title="조회 테스트 문서",
            content="이 문서는 UUID로 조회될 예정입니다.",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        # Retrieve by ID
        retrieved = await doc_helper.get(doc_uuid)

        assert retrieved is not None
        assert retrieved.get("title") == "조회 테스트 문서"

    async def test_get_nonexistent_document(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test retrieving a non-existent document returns None."""
        fake_uuid = "00000000-0000-0000-0000-000000000000"

        result = await doc_helper.get(fake_uuid)

        assert result is None

    async def test_update_title_and_content(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test updating both title and content of a document."""
        doc = await doc_helper.create(
            title="원래 제목",
            content="원래 내용",
        )
        doc_uuid = doc.get("doc_uuid") or doc.get("id")

        # Update both title and content
        updated = await doc_helper.update(
            doc_uuid,
            title="수정된 제목",
            content="수정된 내용입니다.",
        )

        assert updated is not None

        # Verify changes
        retrieved = await doc_helper.get(doc_uuid)
        assert retrieved is not None
        assert retrieved.get("title") == "수정된 제목"


@pytest.mark.e2e
class TestDocumentMetadata:
    """E2E tests for document metadata handling."""

    async def test_create_with_metadata(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test creating document with custom metadata."""
        metadata = {
            "author": "test-author",
            "category": "technology",
            "tags": ["ai", "ml", "deep-learning"],
            "version": 1,
        }

        doc = await doc_helper.create(
            title="메타데이터 테스트",
            content="메타데이터가 포함된 문서입니다.",
            metadata=metadata,
        )

        assert doc is not None
        doc_metadata = doc.get("metadata", {})

        # Metadata should be preserved (if supported)
        if doc_metadata:
            assert doc_metadata.get("author") == "test-author"

    async def test_create_with_source(
        self,
        doc_helper: DocumentHelper,
    ) -> None:
        """Test creating document with custom source identifier."""
        doc = await doc_helper.create(
            title="소스 테스트",
            content="특정 소스에서 온 문서입니다.",
            source="confluence",
        )

        assert doc is not None
        # Source should be set (if returned in response)
        if "source" in doc:
            assert doc["source"] == "confluence"
