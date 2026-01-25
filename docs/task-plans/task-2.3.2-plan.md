# Task Execution Plan: 2.3.2 - ACL Service 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.3.2 |
| **Task Name** | ACL Service 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 2.2.1 |

### Description
ACL 기반 권한 확인 및 필터링 서비스를 구현합니다.

### Acceptance Criteria
- [ ] `src/services/acl_service.py` 생성
- [ ] 접근 가능한 문서 ID 목록 조회
- [ ] 특정 문서 권한 확인
- [ ] 캐싱 고려 (향후 확장)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.3 ACL Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-2

### 2.2 ACL 모델 (PostgreSQL)
```sql
-- acl_entries 테이블
CREATE TABLE acl_entries (
    id SERIAL PRIMARY KEY,
    doc_uuid UUID NOT NULL REFERENCES documents(doc_uuid),
    principal_type VARCHAR(10) NOT NULL, -- 'user', 'group', 'org'
    principal_id VARCHAR(100) NOT NULL,
    permission VARCHAR(20) NOT NULL,     -- 'read', 'write', 'admin'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.3 접근 권한 로직
사용자가 문서에 접근 가능한 조건:
1. `principal_type='user' AND principal_id=user_id`
2. `principal_type='group' AND principal_id IN user_groups`
3. `principal_type='org' AND principal_id='ALL'` (전사 공개)

### 2.4 설계 결정
1. **Repository 의존**: PostgresRepository 활용
2. **Milvus Filter 생성**: 검색 시 doc_uuid 필터 표현식 생성
3. **캐싱 준비**: 캐시 인터페이스 정의 (Redis 향후 적용)
4. **Permission 계층**: read ⊂ write ⊂ admin

### 2.5 클래스 구조
```
AclService
├── __init__(postgres_repo, cache?)
├── get_accessible_documents(user_id, groups) -> list[str]
├── get_accessible_documents_filter(user_id, groups) -> str
├── check_access(user_id, groups, doc_uuid, permission) -> bool
├── grant_access(doc_uuid, principal_type, principal_id, permission)
└── revoke_access(doc_uuid, principal_type, principal_id)
```

---

## 3. Implementation Steps

### Step 1: ACL 모델 및 기본 서비스 구조 (1h)

**작업 내용:**
1. ACL 엔티티 모델 정의
2. AclService 클래스 기본 구조
3. Permission 열거형 정의

**src/domain/models/acl.py:**
```python
"""ACL domain models."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal


class PrincipalType(str, Enum):
    """Type of principal."""

    USER = "user"
    GROUP = "group"
    ORG = "org"


class Permission(str, Enum):
    """Permission level."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

    def includes(self, other: "Permission") -> bool:
        """Check if this permission includes another.

        admin > write > read
        """
        hierarchy = {
            Permission.READ: 0,
            Permission.WRITE: 1,
            Permission.ADMIN: 2,
        }
        return hierarchy[self] >= hierarchy[other]


@dataclass
class AclEntry:
    """ACL entry model."""

    doc_uuid: str
    principal_type: PrincipalType
    principal_id: str
    permission: Permission
    id: int | None = None
    created_at: datetime | None = None
```

**src/services/acl_service.py:**
```python
"""ACL service for access control."""
from typing import Protocol

from src.domain.models.acl import AclEntry, Permission, PrincipalType


class AclRepositoryProtocol(Protocol):
    """Protocol for ACL repository."""

    async def get_accessible_doc_uuids(
        self,
        user_id: str,
        user_groups: list[str],
    ) -> list[str]:
        """Get accessible document UUIDs for user."""
        ...

    async def check_document_access(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str],
        permission: Permission,
    ) -> bool:
        """Check if user has permission on document."""
        ...

    async def create_acl_entry(self, entry: AclEntry) -> AclEntry:
        """Create ACL entry."""
        ...

    async def delete_acl_entry(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
    ) -> bool:
        """Delete ACL entry."""
        ...


class AclService:
    """Service for ACL-based access control."""

    def __init__(self, repository: AclRepositoryProtocol) -> None:
        """Initialize ACL service.

        Args:
            repository: ACL repository implementation
        """
        self._repository = repository
```

**완료 기준:**
- [ ] Permission, PrincipalType 열거형 정의
- [ ] AclEntry 모델 정의
- [ ] AclRepositoryProtocol 정의
- [ ] AclService 기본 구조

---

### Step 2: 문서 접근 권한 조회 (1.5h)

**작업 내용:**
1. get_accessible_documents 구현
2. Milvus 필터 표현식 생성
3. 빈 결과 처리

**src/services/acl_service.py (계속):**
```python
    async def get_accessible_documents(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> list[str]:
        """Get list of accessible document UUIDs.

        Checks:
        1. user principal matches user_id
        2. group principal matches any of user_groups
        3. org principal is 'ALL' (public)

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to

        Returns:
            List of accessible document UUIDs
        """
        groups = user_groups or []
        return await self._repository.get_accessible_doc_uuids(user_id, groups)

    def build_milvus_filter(self, doc_uuids: list[str]) -> str:
        """Build Milvus filter expression for accessible documents.

        Args:
            doc_uuids: List of accessible document UUIDs

        Returns:
            Milvus filter expression string

        Note:
            Returns "doc_uuid in []" for empty list (matches nothing)
        """
        if not doc_uuids:
            # Return expression that matches nothing
            return 'doc_uuid == "__NONE__"'

        # Escape quotes in UUIDs (should be standard format)
        escaped = [f'"{uuid}"' for uuid in doc_uuids]
        return f"doc_uuid in [{', '.join(escaped)}]"

    async def get_accessible_documents_filter(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> str:
        """Get Milvus filter expression for accessible documents.

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to

        Returns:
            Milvus filter expression
        """
        doc_uuids = await self.get_accessible_documents(user_id, user_groups)
        return self.build_milvus_filter(doc_uuids)
```

**완료 기준:**
- [ ] get_accessible_documents 구현
- [ ] build_milvus_filter 구현
- [ ] get_accessible_documents_filter 구현

---

### Step 3: 권한 확인 및 관리 (1h)

**작업 내용:**
1. check_access 구현 (특정 문서 권한 확인)
2. grant_access 구현
3. revoke_access 구현

**src/services/acl_service.py (계속):**
```python
    async def check_access(
        self,
        user_id: str,
        user_groups: list[str] | None,
        doc_uuid: str,
        permission: Permission = Permission.READ,
    ) -> bool:
        """Check if user has permission on specific document.

        Args:
            user_id: User identifier
            user_groups: List of group IDs user belongs to
            doc_uuid: Document UUID to check
            permission: Required permission level

        Returns:
            True if user has the required permission
        """
        groups = user_groups or []
        return await self._repository.check_document_access(
            doc_uuid=doc_uuid,
            user_id=user_id,
            user_groups=groups,
            permission=permission,
        )

    async def grant_access(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
        permission: Permission = Permission.READ,
    ) -> AclEntry:
        """Grant access to a document.

        Args:
            doc_uuid: Document UUID
            principal_type: Type of principal (user, group, org)
            principal_id: Principal identifier
            permission: Permission to grant

        Returns:
            Created ACL entry
        """
        entry = AclEntry(
            doc_uuid=doc_uuid,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
        )
        return await self._repository.create_acl_entry(entry)

    async def revoke_access(
        self,
        doc_uuid: str,
        principal_type: PrincipalType,
        principal_id: str,
    ) -> bool:
        """Revoke access from a document.

        Args:
            doc_uuid: Document UUID
            principal_type: Type of principal
            principal_id: Principal identifier

        Returns:
            True if entry was deleted
        """
        return await self._repository.delete_acl_entry(
            doc_uuid=doc_uuid,
            principal_type=principal_type,
            principal_id=principal_id,
        )

    async def grant_public_access(
        self,
        doc_uuid: str,
        permission: Permission = Permission.READ,
    ) -> AclEntry:
        """Grant public (organization-wide) access.

        Args:
            doc_uuid: Document UUID
            permission: Permission to grant

        Returns:
            Created ACL entry
        """
        return await self.grant_access(
            doc_uuid=doc_uuid,
            principal_type=PrincipalType.ORG,
            principal_id="ALL",
            permission=permission,
        )
```

**완료 기준:**
- [ ] check_access 구현
- [ ] grant_access 구현
- [ ] revoke_access 구현
- [ ] grant_public_access 편의 메서드

---

### Step 4: Factory 및 테스트 (0.5h)

**작업 내용:**
1. Service factory 함수
2. 테스트 작성

**src/services/acl_service.py (추가):**
```python
# Service factory
_service: AclService | None = None


def get_acl_service(repository: AclRepositoryProtocol | None = None) -> AclService:
    """Get or create ACL service.

    Args:
        repository: Repository instance (only used on first call)

    Returns:
        AclService instance
    """
    global _service
    if _service is None:
        if repository is None:
            raise ValueError("Repository required for first initialization")
        _service = AclService(repository)
    return _service


def reset_acl_service() -> None:
    """Reset ACL service singleton (for testing)."""
    global _service
    _service = None
```

**tests/unit/test_services/test_acl_service.py:**
```python
"""Tests for ACL service."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.acl_service import AclService
from src.domain.models.acl import AclEntry, Permission, PrincipalType


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create mock repository."""
    return MagicMock()


@pytest.fixture
def acl_service(mock_repository: MagicMock) -> AclService:
    """Create ACL service with mock repository."""
    return AclService(mock_repository)


class TestAclService:
    """Tests for AclService."""

    async def test_get_accessible_documents(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test getting accessible documents."""
        mock_repository.get_accessible_doc_uuids = AsyncMock(
            return_value=["uuid1", "uuid2"]
        )

        result = await acl_service.get_accessible_documents("user1", ["group1"])

        assert result == ["uuid1", "uuid2"]
        mock_repository.get_accessible_doc_uuids.assert_called_once_with(
            "user1", ["group1"]
        )

    def test_build_milvus_filter(self, acl_service: AclService) -> None:
        """Test building Milvus filter."""
        filter_expr = acl_service.build_milvus_filter(["uuid1", "uuid2"])
        assert 'doc_uuid in ["uuid1", "uuid2"]' == filter_expr

    def test_build_milvus_filter_empty(self, acl_service: AclService) -> None:
        """Test building filter for empty list."""
        filter_expr = acl_service.build_milvus_filter([])
        assert filter_expr == 'doc_uuid == "__NONE__"'

    async def test_check_access(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test checking access."""
        mock_repository.check_document_access = AsyncMock(return_value=True)

        result = await acl_service.check_access(
            user_id="user1",
            user_groups=["group1"],
            doc_uuid="doc-uuid",
            permission=Permission.READ,
        )

        assert result is True

    async def test_grant_access(
        self,
        acl_service: AclService,
        mock_repository: MagicMock,
    ) -> None:
        """Test granting access."""
        expected_entry = AclEntry(
            id=1,
            doc_uuid="doc-uuid",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
        )
        mock_repository.create_acl_entry = AsyncMock(return_value=expected_entry)

        result = await acl_service.grant_access(
            doc_uuid="doc-uuid",
            principal_type=PrincipalType.USER,
            principal_id="user1",
            permission=Permission.READ,
        )

        assert result.id == 1


class TestPermission:
    """Tests for Permission enum."""

    def test_admin_includes_read(self) -> None:
        """Test admin includes read."""
        assert Permission.ADMIN.includes(Permission.READ)

    def test_admin_includes_write(self) -> None:
        """Test admin includes write."""
        assert Permission.ADMIN.includes(Permission.WRITE)

    def test_read_not_includes_write(self) -> None:
        """Test read does not include write."""
        assert not Permission.READ.includes(Permission.WRITE)
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_get_accessible_documents` | 접근 가능 문서 조회 | UUID 리스트 반환 |
| `test_build_milvus_filter` | 필터 표현식 생성 | 유효한 Milvus 표현식 |
| `test_build_milvus_filter_empty` | 빈 리스트 필터 | __NONE__ 조건 |
| `test_check_access` | 권한 확인 | True/False |
| `test_grant_access` | 권한 부여 | AclEntry 반환 |
| `test_revoke_access` | 권한 취소 | True |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_user_access` | 사용자 직접 권한 | 접근 허용 |
| `test_group_access` | 그룹 통한 권한 | 접근 허용 |
| `test_org_all_access` | 전사 공개 권한 | 모든 사용자 접근 |
| `test_no_access` | 권한 없음 | 접근 거부 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 대량 문서 시 성능 저하 | High | Medium | 페이지네이션, 캐싱 적용 |
| ACL 규칙 복잡도 | Medium | Low | 명확한 규칙 문서화 |
| 캐시 무효화 | Medium | Medium | 권한 변경 시 캐시 무효화 로직 |

---

## 6. Definition of Done

- [ ] `src/services/acl_service.py` 구현
- [ ] `src/domain/models/acl.py` 구현
- [ ] get_accessible_documents 구현
- [ ] build_milvus_filter 구현
- [ ] check_access 구현
- [ ] grant_access / revoke_access 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: ACL 모델 및 기본 구조 | 1h | - |
| Step 2: 문서 접근 권한 조회 | 1.5h | - |
| Step 3: 권한 확인 및 관리 | 1h | - |
| Step 4: Factory 및 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
