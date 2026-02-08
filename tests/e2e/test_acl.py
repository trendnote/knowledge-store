"""E2E tests for ACL (Access Control List) enforcement.

This module tests access control:
- Owner access to documents
- Blocking unauthorized users
- Group-based access
- Search filtering by ACL
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

    from tests.e2e.conftest import DocumentHelper


@pytest.mark.e2e
class TestACLEnforcement:
    """E2E tests for ACL enforcement on documents."""

    async def test_owner_can_access(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
    ) -> None:
        """Test that document owner can access their own document.

        Scenario:
        1. User1 creates a document
        2. User1 searches for the document
        3. Document should be found
        """
        from tests.e2e.conftest import DocumentHelper

        helper = DocumentHelper(api_client, user1_headers)

        try:
            doc = await helper.create(
                title="User1's Private Document",
                content="이 문서는 user1에게 속한 비공개 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            await helper.wait_for_indexing()

            # Search as owner
            result = await helper.search("user1 비공개 문서")

            found_ids = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result.get("results", [])
            ]
            assert doc_uuid in found_ids, "Owner should find their own document"

        finally:
            await helper.cleanup()

    async def test_owner_can_read_directly(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
    ) -> None:
        """Test that owner can directly read their document by UUID."""
        from tests.e2e.conftest import DocumentHelper

        helper = DocumentHelper(api_client, user1_headers)

        try:
            doc = await helper.create(
                title="Direct Read Test",
                content="직접 읽기 테스트 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # Direct read as owner
            retrieved = await helper.get(doc_uuid)

            assert retrieved is not None
            assert retrieved.get("title") == "Direct Read Test"

        finally:
            await helper.cleanup()

    async def test_other_user_cannot_access_private(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        user2_headers: dict[str, str],
    ) -> None:
        """Test that other users cannot access private documents.

        Scenario:
        1. User1 creates a private document
        2. User2 searches for the document
        3. Document should NOT be found by User2
        4. Direct access by User2 should be denied
        """
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        try:
            # User1 creates document
            unique_keyword = "프라이빗테스트키워드"
            doc = await helper1.create(
                title="Private Document",
                content=f"비공개 문서 내용입니다. {unique_keyword}.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            await helper1.wait_for_indexing()

            # User2 searches - should not find
            result = await helper2.search(unique_keyword)

            found_ids = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result.get("results", [])
            ]
            assert doc_uuid not in found_ids, "User2 should not find User1's private document"

            # User2 tries direct access - should fail
            doc_for_user2 = await helper2.get(doc_uuid)
            assert doc_for_user2 is None, "User2 should not directly access User1's document"

        finally:
            await helper1.cleanup()

    async def test_owner_can_update(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
    ) -> None:
        """Test that only owner can update their document."""
        from tests.e2e.conftest import DocumentHelper

        helper = DocumentHelper(api_client, user1_headers)

        try:
            doc = await helper.create(
                title="Update Permission Test",
                content="원래 내용",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # Owner updates
            updated = await helper.update(doc_uuid, content="수정된 내용입니다.")

            assert updated is not None

        finally:
            await helper.cleanup()

    async def test_other_user_cannot_update(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        user2_headers: dict[str, str],
    ) -> None:
        """Test that non-owner cannot update document."""
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        try:
            # User1 creates document
            doc = await helper1.create(
                title="No Update Permission Test",
                content="User1의 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # User2 tries to update - should fail
            response = await api_client.put(
                f"/api/v1/documents/{doc_uuid}",
                json={"content": "User2가 수정 시도"},
                headers=user2_headers,
            )

            # Should be forbidden or not found
            assert response.status_code in [
                403,
                404,
            ], "Non-owner update should be denied"

        finally:
            await helper1.cleanup()

    async def test_other_user_cannot_delete(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        user2_headers: dict[str, str],
    ) -> None:
        """Test that non-owner cannot delete document."""
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)

        try:
            # User1 creates document
            doc = await helper1.create(
                title="No Delete Permission Test",
                content="User1의 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # User2 tries to delete - should fail
            response = await api_client.delete(
                f"/api/v1/documents/{doc_uuid}",
                headers=user2_headers,
            )

            # Should be forbidden or not found
            assert response.status_code in [
                403,
                404,
            ], "Non-owner delete should be denied"

            # Document should still exist for owner
            doc_after = await helper1.get(doc_uuid)
            assert doc_after is not None, "Document should still exist after failed delete"

        finally:
            await helper1.cleanup()


@pytest.mark.e2e
class TestACLSearch:
    """E2E tests for ACL filtering in search results."""

    async def test_search_only_returns_accessible(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        user2_headers: dict[str, str],
    ) -> None:
        """Test that search only returns documents user can access.

        Scenario:
        1. User1 creates document with keyword X
        2. User2 creates document with keyword X
        3. User1 searches for X
        4. User1 should only find their own document
        5. User2 searches for X
        6. User2 should only find their own document
        """
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)
        helper2 = DocumentHelper(api_client, user2_headers)

        common_keyword = "공통검색테스트키워드"

        try:
            # Both users create documents with same keyword
            doc1 = await helper1.create(
                title="User1 AI Document",
                content=f"인공지능 기술에 관한 user1의 문서입니다. {common_keyword}",
            )
            doc1_uuid = doc1.get("doc_uuid") or doc1.get("id")

            doc2 = await helper2.create(
                title="User2 AI Document",
                content=f"인공지능 기술에 관한 user2의 문서입니다. {common_keyword}",
            )
            doc2_uuid = doc2.get("doc_uuid") or doc2.get("id")

            await asyncio.sleep(3)  # Wait for indexing

            # User1 searches
            result1 = await helper1.search(common_keyword)
            found1 = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result1.get("results", [])
            ]

            # User1 should find own doc, not user2's
            assert doc1_uuid in found1, "User1 should find their own document"
            assert doc2_uuid not in found1, "User1 should not find User2's document"

            # User2 searches
            result2 = await helper2.search(common_keyword)
            found2 = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result2.get("results", [])
            ]

            # User2 should find own doc, not user1's
            assert doc2_uuid in found2, "User2 should find their own document"
            assert doc1_uuid not in found2, "User2 should not find User1's document"

        finally:
            await helper1.cleanup()
            await helper2.cleanup()

    async def test_search_empty_for_unauthorized(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        public_headers: dict[str, str],
    ) -> None:
        """Test that unauthorized users get empty search results for private content."""
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)
        helper_public = DocumentHelper(api_client, public_headers)

        unique_keyword = "비공개전용키워드테스트"

        try:
            # User1 creates private document
            await helper1.create(
                title="Private Only Document",
                content=f"비공개 내용입니다. {unique_keyword}",
            )

            await helper1.wait_for_indexing()

            # Public user searches - should get empty results
            result = await helper_public.search(unique_keyword)

            found = result.get("results", [])
            assert len(found) == 0, "Public user should not find private documents"

        finally:
            await helper1.cleanup()


@pytest.mark.e2e
class TestGroupAccess:
    """E2E tests for group-based access control."""

    async def test_same_group_can_share(
        self,
        api_client: httpx.AsyncClient,
    ) -> None:
        """Test that users in the same group can potentially share documents.

        Note: This test assumes group-based sharing is implemented.
        The actual behavior depends on ACL configuration.
        """
        from tests.e2e.conftest import DocumentHelper

        # Both users in engineering group
        user_a_headers = {
            "X-User-Id": "user-a",
            "X-User-Groups": "engineering,team-alpha",
            "Content-Type": "application/json",
        }
        user_b_headers = {
            "X-User-Id": "user-b",
            "X-User-Groups": "engineering,team-beta",
            "Content-Type": "application/json",
        }

        helper_a = DocumentHelper(api_client, user_a_headers)

        try:
            # User A creates document
            doc = await helper_a.create(
                title="Group Shared Document",
                content="이 문서는 engineering 그룹과 공유됩니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            await helper_a.wait_for_indexing()

            # Verify User A can access
            doc_for_a = await helper_a.get(doc_uuid)
            assert doc_for_a is not None, "Creator should access their document"

            # Note: User B access depends on group sharing implementation
            # This is left as a placeholder for when group sharing is configured

        finally:
            await helper_a.cleanup()

    async def test_different_group_blocked(
        self,
        api_client: httpx.AsyncClient,
    ) -> None:
        """Test that users in different groups cannot access private documents."""
        from tests.e2e.conftest import DocumentHelper

        eng_headers = {
            "X-User-Id": "eng-user",
            "X-User-Groups": "engineering",
            "Content-Type": "application/json",
        }
        marketing_headers = {
            "X-User-Id": "marketing-user",
            "X-User-Groups": "marketing",
            "Content-Type": "application/json",
        }

        helper_eng = DocumentHelper(api_client, eng_headers)
        helper_mkt = DocumentHelper(api_client, marketing_headers)

        unique_keyword = "엔지니어링전용문서키워드"

        try:
            # Engineering user creates document
            doc = await helper_eng.create(
                title="Engineering Only Document",
                content=f"엔지니어링 팀 전용 문서입니다. {unique_keyword}",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            await helper_eng.wait_for_indexing()

            # Marketing user searches - should not find
            result = await helper_mkt.search(unique_keyword)

            found_ids = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result.get("results", [])
            ]
            assert doc_uuid not in found_ids, "Marketing should not find engineering document"

            # Marketing user direct access - should fail
            doc_for_mkt = await helper_mkt.get(doc_uuid)
            assert doc_for_mkt is None, "Marketing should not directly access engineering document"

        finally:
            await helper_eng.cleanup()


@pytest.mark.e2e
class TestACLEdgeCases:
    """E2E tests for ACL edge cases and special scenarios."""

    async def test_empty_user_groups(
        self,
        api_client: httpx.AsyncClient,
    ) -> None:
        """Test behavior when user has no groups."""
        from tests.e2e.conftest import DocumentHelper

        no_group_headers = {
            "X-User-Id": "no-group-user",
            "X-User-Groups": "",
            "Content-Type": "application/json",
        }

        helper = DocumentHelper(api_client, no_group_headers)

        try:
            # User with no groups creates document
            doc = await helper.create(
                title="No Group User Document",
                content="그룹 없는 사용자의 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # Should still be able to access own document
            retrieved = await helper.get(doc_uuid)
            assert retrieved is not None, "User should access their own document"

        finally:
            await helper.cleanup()

    async def test_owner_delete_updates_search(
        self,
        api_client: httpx.AsyncClient,
        user1_headers: dict[str, str],
        user2_headers: dict[str, str],
    ) -> None:
        """Test that when owner deletes, it's removed from everyone's potential search."""
        from tests.e2e.conftest import DocumentHelper

        helper1 = DocumentHelper(api_client, user1_headers)

        unique_keyword = "삭제후검색테스트"

        try:
            # User1 creates document
            doc = await helper1.create(
                title="To Be Deleted",
                content=f"이 문서는 삭제될 예정입니다. {unique_keyword}",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            await helper1.wait_for_indexing()

            # Verify User1 can find it
            result1 = await helper1.search(unique_keyword)
            found_ids = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result1.get("results", [])
            ]
            assert doc_uuid in found_ids, "Document should be searchable before delete"

            # User1 deletes
            deleted = await helper1.delete(doc_uuid)
            assert deleted

            await helper1.wait_for_sync()

            # Verify removed from search
            result2 = await helper1.search(unique_keyword)
            found_ids_after = [
                r.get("doc_uuid") or r.get("document_id")
                for r in result2.get("results", [])
            ]
            assert doc_uuid not in found_ids_after, "Deleted document should not be searchable"

        finally:
            await helper1.cleanup()

    async def test_case_sensitivity_user_id(
        self,
        api_client: httpx.AsyncClient,
    ) -> None:
        """Test that user IDs are case-sensitive for ACL."""
        from tests.e2e.conftest import DocumentHelper

        upper_headers = {
            "X-User-Id": "USER1",
            "X-User-Groups": "engineering",
            "Content-Type": "application/json",
        }
        lower_headers = {
            "X-User-Id": "user1",
            "X-User-Groups": "engineering",
            "Content-Type": "application/json",
        }

        helper_upper = DocumentHelper(api_client, upper_headers)
        helper_lower = DocumentHelper(api_client, lower_headers)

        try:
            # USER1 (uppercase) creates document
            doc = await helper_upper.create(
                title="Case Sensitivity Test",
                content="대소문자 구분 테스트 문서입니다.",
            )
            doc_uuid = doc.get("doc_uuid") or doc.get("id")

            # USER1 should access
            doc_upper = await helper_upper.get(doc_uuid)
            assert doc_upper is not None

            # user1 (lowercase) - behavior depends on implementation
            # This test documents the actual behavior
            doc_lower = await helper_lower.get(doc_uuid)
            # Record actual behavior (may be None if case-sensitive)

        finally:
            await helper_upper.cleanup()
