"""Tests for ACL service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.acl_service import (
    AclEntryData,
    AclService,
    Permission,
    PrincipalType,
    close_acl_service,
    get_acl_service,
    reset_acl_service,
)


class TestPermission:
    """Tests for Permission enum."""

    def test_permission_values(self) -> None:
        """Test permission enum values."""
        assert Permission.READ.value == "read"
        assert Permission.WRITE.value == "write"
        assert Permission.DELETE.value == "delete"
        assert Permission.ADMIN.value == "admin"

    def test_admin_includes_read(self) -> None:
        """Test admin includes read permission."""
        assert Permission.ADMIN.includes(Permission.READ)

    def test_admin_includes_write(self) -> None:
        """Test admin includes write permission."""
        assert Permission.ADMIN.includes(Permission.WRITE)

    def test_admin_includes_delete(self) -> None:
        """Test admin includes delete permission."""
        assert Permission.ADMIN.includes(Permission.DELETE)

    def test_admin_includes_admin(self) -> None:
        """Test admin includes admin (itself)."""
        assert Permission.ADMIN.includes(Permission.ADMIN)

    def test_write_includes_read(self) -> None:
        """Test write includes read permission."""
        assert Permission.WRITE.includes(Permission.READ)

    def test_write_not_includes_delete(self) -> None:
        """Test write does not include delete."""
        assert not Permission.WRITE.includes(Permission.DELETE)

    def test_write_not_includes_admin(self) -> None:
        """Test write does not include admin."""
        assert not Permission.WRITE.includes(Permission.ADMIN)

    def test_read_includes_read(self) -> None:
        """Test read includes itself."""
        assert Permission.READ.includes(Permission.READ)

    def test_read_not_includes_write(self) -> None:
        """Test read does not include write."""
        assert not Permission.READ.includes(Permission.WRITE)

    def test_delete_includes_write(self) -> None:
        """Test delete includes write."""
        assert Permission.DELETE.includes(Permission.WRITE)

    def test_delete_not_includes_admin(self) -> None:
        """Test delete does not include admin."""
        assert not Permission.DELETE.includes(Permission.ADMIN)


class TestPrincipalType:
    """Tests for PrincipalType enum."""

    def test_principal_type_values(self) -> None:
        """Test principal type enum values."""
        assert PrincipalType.USER.value == "user"
        assert PrincipalType.GROUP.value == "group"
        assert PrincipalType.ORG.value == "org"
        assert PrincipalType.ROLE.value == "role"

    def test_principal_type_is_string(self) -> None:
        """Test principal type can be used as string."""
        assert str(PrincipalType.USER) == "PrincipalType.USER"
        assert PrincipalType.USER == "user"


class TestAclEntryData:
    """Tests for AclEntryData dataclass."""

    def test_create_basic_entry(self) -> None:
        """Test creating basic ACL entry."""
        entry = AclEntryData(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
        )

        assert entry.doc_uuid == "doc-123"
        assert entry.principal_type == PrincipalType.USER
        assert entry.principal_id == "user1"
        assert entry.permission == Permission.READ
        assert entry.id is None
        assert entry.granted_by is None
        assert entry.expires_at is None
        assert entry.created_at is None

    def test_create_full_entry(self) -> None:
        """Test creating ACL entry with all fields."""
        now = datetime.now(tz=UTC)
        expires = now + timedelta(days=30)

        entry = AclEntryData(
            doc_uuid="doc-123",
            principal_type=PrincipalType.GROUP,
            principal_id="group1",
            permission=Permission.WRITE,
            id=1,
            granted_by="admin",
            expires_at=expires,
            created_at=now,
        )

        assert entry.id == 1
        assert entry.granted_by == "admin"
        assert entry.expires_at == expires
        assert entry.created_at == now


class TestAclServiceGetAccessibleDocuments:
    """Tests for AclService.get_accessible_documents."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_get_accessible_documents(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting accessible documents."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(
            return_value=["uuid1", "uuid2", "uuid3"]
        )

        result = await acl_service.get_accessible_documents("user1", ["group1", "group2"])

        assert result == ["uuid1", "uuid2", "uuid3"]
        mock_repository.get_accessible_doc_uuids.assert_called_once_with(
            "user1", ["group1", "group2"]
        )

    @pytest.mark.asyncio
    async def test_get_accessible_documents_no_groups(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting accessible documents with no groups."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(return_value=["uuid1"])

        result = await acl_service.get_accessible_documents("user1")

        assert result == ["uuid1"]
        mock_repository.get_accessible_doc_uuids.assert_called_once_with("user1", [])

    @pytest.mark.asyncio
    async def test_get_accessible_documents_empty_result(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting accessible documents returns empty list."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(return_value=[])

        result = await acl_service.get_accessible_documents("user1", ["group1"])

        assert result == []


class TestAclServiceBuildMilvusFilter:
    """Tests for AclService.build_milvus_filter."""

    @pytest.fixture
    def acl_service(self) -> AclService:
        """Create ACL service with mock repository."""
        mock_repository = MagicMock()
        return AclService(mock_repository)

    def test_build_milvus_filter_single_uuid(self, acl_service: AclService) -> None:
        """Test building filter with single UUID."""
        result = acl_service.build_milvus_filter(["uuid1"])

        assert result == 'doc_uuid in ["uuid1"]'

    def test_build_milvus_filter_multiple_uuids(self, acl_service: AclService) -> None:
        """Test building filter with multiple UUIDs."""
        result = acl_service.build_milvus_filter(["uuid1", "uuid2", "uuid3"])

        assert result == 'doc_uuid in ["uuid1", "uuid2", "uuid3"]'

    def test_build_milvus_filter_empty_list(self, acl_service: AclService) -> None:
        """Test building filter with empty list."""
        result = acl_service.build_milvus_filter([])

        assert result == 'doc_uuid == "__NONE__"'

    def test_build_milvus_filter_uuid_format(self, acl_service: AclService) -> None:
        """Test building filter with UUID format."""
        uuids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ]
        result = acl_service.build_milvus_filter(uuids)

        assert (
            result
            == 'doc_uuid in ["550e8400-e29b-41d4-a716-446655440000", "6ba7b810-9dad-11d1-80b4-00c04fd430c8"]'
        )


class TestAclServiceGetAccessibleDocumentsFilter:
    """Tests for AclService.get_accessible_documents_filter."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_get_accessible_documents_filter(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting filter expression."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(
            return_value=["uuid1", "uuid2"]
        )

        result = await acl_service.get_accessible_documents_filter("user1", ["group1"])

        assert result == 'doc_uuid in ["uuid1", "uuid2"]'

    @pytest.mark.asyncio
    async def test_get_accessible_documents_filter_empty(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting filter expression with no accessible documents."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(return_value=[])

        result = await acl_service.get_accessible_documents_filter("user1")

        assert result == 'doc_uuid == "__NONE__"'


class TestAclServiceCheckAccess:
    """Tests for AclService.check_access."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_check_access_granted(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test checking access when granted."""
        mock_repository.check_document_access = AsyncMock(return_value=True)

        result = await acl_service.check_access(
            user_id="user1",
            user_groups=["group1"],
            doc_uuid="doc-123",
            permission=Permission.READ,
        )

        assert result is True
        mock_repository.check_document_access.assert_called_once_with(
            doc_uuid="doc-123",
            user_id="user1",
            user_groups=["group1"],
            permission=Permission.READ,
        )

    @pytest.mark.asyncio
    async def test_check_access_denied(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test checking access when denied."""
        mock_repository.check_document_access = AsyncMock(return_value=False)

        result = await acl_service.check_access(
            user_id="user1",
            user_groups=["group1"],
            doc_uuid="doc-123",
            permission=Permission.ADMIN,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_check_access_default_permission(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test checking access with default READ permission."""
        mock_repository.check_document_access = AsyncMock(return_value=True)

        result = await acl_service.check_access(
            user_id="user1",
            user_groups=None,
            doc_uuid="doc-123",
        )

        assert result is True
        mock_repository.check_document_access.assert_called_once_with(
            doc_uuid="doc-123",
            user_id="user1",
            user_groups=[],
            permission=Permission.READ,
        )


class TestAclServiceGrantAccess:
    """Tests for AclService.grant_access."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_grant_access_user(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting access to user."""
        expected_entry = AclEntryData(
            id=1,
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
        )

        assert result.id == 1
        assert result.principal_type == PrincipalType.USER

    @pytest.mark.asyncio
    async def test_grant_access_group(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting access to group."""
        expected_entry = AclEntryData(
            id=2,
            doc_uuid="doc-123",
            principal_type=PrincipalType.GROUP,
            principal_id="team-dev",
            permission=Permission.WRITE,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.GROUP,
            principal_id="team-dev",
            permission=Permission.WRITE,
        )

        assert result.id == 2
        assert result.principal_id == "team-dev"
        assert result.permission == Permission.WRITE

    @pytest.mark.asyncio
    async def test_grant_access_with_expiry(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting access with expiration."""
        expires = datetime.now(tz=UTC) + timedelta(days=30)
        expected_entry = AclEntryData(
            id=3,
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="contractor1",
            permission=Permission.READ,
            expires_at=expires,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="contractor1",
            permission=Permission.READ,
            expires_at=expires,
        )

        assert result.expires_at == expires

    @pytest.mark.asyncio
    async def test_grant_access_with_granted_by(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting access with granted_by field."""
        expected_entry = AclEntryData(
            id=4,
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
            granted_by="admin",
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            granted_by="admin",
        )

        assert result.granted_by == "admin"


class TestAclServiceRevokeAccess:
    """Tests for AclService.revoke_access."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_revoke_access_success(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test revoking access successfully."""
        mock_repository.delete_acl_entry = AsyncMock(return_value=True)

        result = await acl_service.revoke_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
        )

        assert result is True
        mock_repository.delete_acl_entry.assert_called_once_with(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="user1",
        )

    @pytest.mark.asyncio
    async def test_revoke_access_not_found(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test revoking access when entry not found."""
        mock_repository.delete_acl_entry = AsyncMock(return_value=False)

        result = await acl_service.revoke_access(
            doc_uuid="doc-123",
            principal_type=PrincipalType.USER,
            principal_id="nonexistent",
        )

        assert result is False


class TestAclServiceGrantPublicAccess:
    """Tests for AclService.grant_public_access."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_grant_public_access(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting public access."""
        expected_entry = AclEntryData(
            id=1,
            doc_uuid="doc-123",
            principal_type=PrincipalType.ORG,
            principal_id="ALL",
            permission=Permission.READ,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_public_access(
            doc_uuid="doc-123",
            permission=Permission.READ,
        )

        assert result.principal_type == PrincipalType.ORG
        assert result.principal_id == "ALL"
        assert result.permission == Permission.READ

    @pytest.mark.asyncio
    async def test_grant_public_access_with_write(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting public write access."""
        expected_entry = AclEntryData(
            id=2,
            doc_uuid="doc-123",
            principal_type=PrincipalType.ORG,
            principal_id="ALL",
            permission=Permission.WRITE,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_public_access(
            doc_uuid="doc-123",
            permission=Permission.WRITE,
            granted_by="admin",
        )

        assert result.permission == Permission.WRITE


class TestAclServiceGetDocumentAcl:
    """Tests for AclService.get_document_acl."""

    @pytest.fixture
    def mock_repository(self) -> MagicMock:
        """Create mock repository."""
        return MagicMock()

    @pytest.fixture
    def acl_service(self, mock_repository: MagicMock) -> AclService:
        """Create ACL service with mock repository."""
        return AclService(mock_repository)

    @pytest.mark.asyncio
    async def test_get_document_acl(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting document ACL entries."""
        entries = [
            AclEntryData(
                id=1,
                doc_uuid="doc-123",
                principal_type=PrincipalType.USER,
                principal_id="user1",
                permission=Permission.READ,
            ),
            AclEntryData(
                id=2,
                doc_uuid="doc-123",
                principal_type=PrincipalType.GROUP,
                principal_id="team-dev",
                permission=Permission.WRITE,
            ),
        ]
        mock_repository.get_document_acl = AsyncMock(return_value=entries)

        result = await acl_service.get_document_acl("doc-123")

        assert len(result) == 2
        assert result[0].principal_id == "user1"
        assert result[1].principal_id == "team-dev"

    @pytest.mark.asyncio
    async def test_get_document_acl_empty(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting document ACL when no entries."""
        mock_repository.get_document_acl = AsyncMock(return_value=[])

        result = await acl_service.get_document_acl("doc-123")

        assert result == []


class TestSingleton:
    """Tests for singleton factory functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_acl_service()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_acl_service()

    def test_get_acl_service_creates_instance(self) -> None:
        """Test get_acl_service creates instance."""
        mock_repository = MagicMock()
        service = get_acl_service(mock_repository)

        assert service is not None
        assert isinstance(service, AclService)

    def test_get_acl_service_returns_same_instance(self) -> None:
        """Test get_acl_service returns same instance."""
        mock_repository = MagicMock()
        service1 = get_acl_service(mock_repository)
        service2 = get_acl_service()

        assert service1 is service2

    def test_get_acl_service_requires_repository_first_call(self) -> None:
        """Test get_acl_service requires repository on first call."""
        with pytest.raises(ValueError, match="Repository required"):
            get_acl_service()

    def test_close_acl_service(self) -> None:
        """Test close_acl_service clears singleton."""
        mock_repository = MagicMock()
        service1 = get_acl_service(mock_repository)

        close_acl_service()

        service2 = get_acl_service(mock_repository)
        assert service1 is not service2

    def test_reset_acl_service(self) -> None:
        """Test reset_acl_service creates new instance."""
        mock_repository = MagicMock()
        service1 = get_acl_service(mock_repository)

        reset_acl_service()

        service2 = get_acl_service(mock_repository)
        assert service1 is not service2
