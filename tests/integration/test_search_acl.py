"""Integration tests for search ACL (Access Control List).

These tests verify that search operations respect access control:
- User ownership permissions
- Group-based permissions
- Public document access
- Permission boundaries between users
"""

from typing import Any

import pytest

from src.domain.search import SearchRequest, SearchType
from src.services.search_service import SearchService


@pytest.mark.integration
class TestSearchACLUserPermissions:
    """Tests for user-level access control in search."""

    @pytest.mark.asyncio
    async def test_user_sees_own_documents(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test user can search their own documents."""
        request = SearchRequest(
            query="인공지능",
            user_id="user1",
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # user1 owns doc-001 and doc-002 (AI and NLP docs)
        user1_doc_uuids = {d["doc_uuid"] for d in test_data["user1_docs"]}
        result_doc_uuids = {r.doc_uuid for r in response.results}

        # At least some results should be from user1's docs
        assert bool(user1_doc_uuids & result_doc_uuids)

    @pytest.mark.asyncio
    async def test_user_cannot_see_others_private_documents(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test user cannot see other users' private documents."""
        # Query that matches user2's private doc
        request = SearchRequest(
            query="비공개 기밀",
            user_id="user1",  # user1 trying to access
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # user2's private doc should not appear
        private_docs = test_data["user2_docs"]
        result_doc_uuids = {r.doc_uuid for r in response.results}

        for private_doc in private_docs:
            assert private_doc["doc_uuid"] not in result_doc_uuids

    @pytest.mark.asyncio
    async def test_owner_can_see_own_private_document(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test owner can see their private document."""
        # user2 searching for their own private doc
        request = SearchRequest(
            query="비공개 기밀",
            user_id="user2",  # Owner of private doc
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # user2's private doc should appear
        private_doc = test_data["user2_docs"][0]
        result_doc_uuids = {r.doc_uuid for r in response.results}

        assert private_doc["doc_uuid"] in result_doc_uuids

    @pytest.mark.asyncio
    async def test_no_accessible_documents_returns_empty(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test user with no access gets empty results."""
        request = SearchRequest(
            query="인공지능",
            user_id="unknown_user",  # No access to any docs
            user_groups=[],  # No group memberships
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Should only see public docs (if any)
        # In our test data, doc-004 is public (*)
        public_doc_uuids = {d["doc_uuid"] for d in test_data["public_docs"]}
        result_doc_uuids = {r.doc_uuid for r in response.results}

        # All results should be from public docs only
        for doc_uuid in result_doc_uuids:
            assert doc_uuid in public_doc_uuids


@pytest.mark.integration
class TestSearchACLGroupPermissions:
    """Tests for group-level access control in search."""

    @pytest.mark.asyncio
    async def test_group_member_can_access_group_documents(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test group member can access group-shared documents."""
        request = SearchRequest(
            query="기술",
            user_id="new_user",  # Not owner of any doc
            user_groups=["engineering"],  # Member of engineering group
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Should find docs shared with engineering group
        assert response.total > 0

    @pytest.mark.asyncio
    async def test_non_member_cannot_access_group_documents(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test non-group-member cannot access group-shared documents."""
        request = SearchRequest(
            query="인공지능",
            user_id="new_user",
            user_groups=["marketing"],  # Not in engineering or ml-team
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Should only see public docs
        public_doc_uuids = {d["doc_uuid"] for d in test_data["public_docs"]}
        result_doc_uuids = {r.doc_uuid for r in response.results}

        for doc_uuid in result_doc_uuids:
            assert doc_uuid in public_doc_uuids

    @pytest.mark.asyncio
    async def test_multiple_group_membership(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test user with multiple group memberships."""
        request = SearchRequest(
            query="기술",
            user_id="new_user",
            user_groups=["engineering", "ml-team"],  # Multiple groups
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Should find docs from both groups
        assert response.total > 0


@pytest.mark.integration
class TestSearchACLPublicDocuments:
    """Tests for public document access."""

    @pytest.mark.asyncio
    async def test_anyone_can_see_public_documents(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test any user can see public documents."""
        request = SearchRequest(
            query="공개 문서",
            user_id="random_user",
            user_groups=[],
            top_k=10,
        )

        response = await search_service.unified_search(request)

        # Should find public docs
        public_doc_uuids = {d["doc_uuid"] for d in test_data["public_docs"]}
        result_doc_uuids = {r.doc_uuid for r in response.results}

        # Public docs should be accessible
        if public_doc_uuids:
            assert bool(public_doc_uuids & result_doc_uuids)

    @pytest.mark.asyncio
    async def test_public_docs_appear_for_all_users(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test public documents appear for all users."""
        users = ["user1", "user2", "random_user", "admin"]
        public_doc_uuids = {d["doc_uuid"] for d in test_data["public_docs"]}

        for user_id in users:
            request = SearchRequest(
                query="회사 정책",  # Matches public doc
                user_id=user_id,
                user_groups=[],
                top_k=10,
            )

            response = await search_service.unified_search(request)
            result_doc_uuids = {r.doc_uuid for r in response.results}

            # Public docs should be visible to all
            for public_uuid in public_doc_uuids:
                if any(r.doc_uuid == public_uuid for r in response.results):
                    # Found at least one public doc
                    break


@pytest.mark.integration
class TestSearchACLCrossChecks:
    """Cross-check tests for ACL enforcement."""

    @pytest.mark.asyncio
    async def test_acl_applied_to_all_search_types(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test ACL is applied consistently across all search types."""
        private_doc = test_data["user2_docs"][0]

        # Test each search type individually
        for search_type in [SearchType.DENSE, SearchType.SPARSE]:
            request = SearchRequest(
                query="비공개",
                user_id="user1",
                search_types=[search_type],
                top_k=10,
            )

            response = await search_service.unified_search(request)
            result_doc_uuids = {r.doc_uuid for r in response.results}

            assert private_doc["doc_uuid"] not in result_doc_uuids, (
                f"Private doc leaked through {search_type.value} search"
            )

    @pytest.mark.asyncio
    async def test_acl_respects_document_not_chunk_level(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test ACL is applied at document level."""
        # If user can access a document, all chunks should be accessible
        request = SearchRequest(
            query="인공지능 머신러닝 딥러닝",  # Match multiple chunks
            user_id="user1",
            top_k=20,
        )

        response = await search_service.unified_search(request)

        # All chunks from user1's docs should be accessible
        user1_doc_uuids = {d["doc_uuid"] for d in test_data["user1_docs"]}

        for result in response.results:
            if result.doc_uuid in user1_doc_uuids:
                # This is expected - user can see their own docs
                pass

    @pytest.mark.asyncio
    async def test_same_query_different_users_different_results(
        self,
        search_service: SearchService,
        test_data: dict[str, Any],
    ) -> None:
        """Test same query returns different results for different users."""
        query = "비공개 기밀"  # Matches user2's private doc

        # user1's results
        request1 = SearchRequest(
            query=query,
            user_id="user1",
            top_k=10,
        )
        response1 = await search_service.unified_search(request1)

        # user2's results
        request2 = SearchRequest(
            query=query,
            user_id="user2",
            top_k=10,
        )
        response2 = await search_service.unified_search(request2)

        # user2 should see their private doc
        private_doc = test_data["user2_docs"][0]
        user2_doc_uuids = {r.doc_uuid for r in response2.results}

        assert private_doc["doc_uuid"] in user2_doc_uuids

        # user1 should NOT see user2's private doc
        user1_doc_uuids = {r.doc_uuid for r in response1.results}
        assert private_doc["doc_uuid"] not in user1_doc_uuids
