# Task 2.3.2: ACL Service 구현

## 작업 정보
- **Task ID**: 2.3.2
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 08:00:37
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/18
- **Task Plan**: docs/task-plans/task-2.3.2-plan.md

## 작업 개요
ACL 기반 권한 확인 및 필터링 서비스를 구현합니다.

## 생성된 파일

### 1. ACL Service
**파일**: `src/services/acl_service.py`

#### Permission Enum
```python
class Permission(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"

    def includes(self, other: Permission) -> bool:
        """Permission hierarchy: ADMIN > DELETE > WRITE > READ"""
        hierarchy = {
            Permission.READ: 0,
            Permission.WRITE: 1,
            Permission.DELETE: 2,
            Permission.ADMIN: 3,
        }
        return hierarchy[self] >= hierarchy[other]
```

#### PrincipalType Enum
```python
class PrincipalType(str, Enum):
    USER = "user"
    GROUP = "group"
    ORG = "org"
    ROLE = "role"
```

#### AclEntryData Dataclass
```python
@dataclass
class AclEntryData:
    doc_uuid: str
    principal_type: PrincipalType
    principal_id: str
    permission: Permission
    id: int | str | None = None
    granted_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
```

#### AclRepositoryProtocol
- `get_accessible_doc_uuids(user_id, user_groups) -> list[str]`
- `check_document_access(doc_uuid, user_id, user_groups, permission) -> bool`
- `create_acl_entry(entry) -> AclEntryData`
- `delete_acl_entry(doc_uuid, principal_type, principal_id) -> bool`
- `get_document_acl(doc_uuid) -> list[AclEntryData]`

#### AclService 클래스
- **Methods**:
  - `get_accessible_documents(user_id, user_groups) -> list[str]`
    - 사용자가 접근 가능한 문서 UUID 목록 조회
  - `build_milvus_filter(doc_uuids) -> str`
    - Milvus 검색용 필터 표현식 생성
    - 빈 리스트: `'doc_uuid == "__NONE__"'`
    - 리스트: `'doc_uuid in ["uuid1", "uuid2"]'`
  - `get_accessible_documents_filter(user_id, user_groups) -> str`
    - 접근 가능 문서 조회 + 필터 생성 통합 메서드
  - `check_access(user_id, user_groups, doc_uuid, permission) -> bool`
    - 특정 문서에 대한 권한 확인
  - `grant_access(doc_uuid, principal_type, principal_id, permission, granted_by, expires_at) -> AclEntryData`
    - 권한 부여
  - `revoke_access(doc_uuid, principal_type, principal_id) -> bool`
    - 권한 취소
  - `grant_public_access(doc_uuid, permission, granted_by) -> AclEntryData`
    - 전사 공개 권한 부여 (org='ALL')
  - `get_document_acl(doc_uuid) -> list[AclEntryData]`
    - 문서의 모든 ACL 엔트리 조회

#### Factory Pattern
- `get_acl_service(repository) -> AclService`
- `close_acl_service() -> None`
- `reset_acl_service() -> None`

**exports 업데이트**: `src/services/__init__.py`

### 2. Unit Tests
**파일**: `tests/unit/test_services/test_acl_service.py`

테스트 클래스:
- `TestPermission`: 12개 테스트 (권한 계층 검증)
- `TestPrincipalType`: 2개 테스트
- `TestAclEntryData`: 2개 테스트
- `TestAclServiceGetAccessibleDocuments`: 3개 테스트
- `TestAclServiceBuildMilvusFilter`: 4개 테스트
- `TestAclServiceGetAccessibleDocumentsFilter`: 2개 테스트
- `TestAclServiceCheckAccess`: 3개 테스트
- `TestAclServiceGrantAccess`: 4개 테스트
- `TestAclServiceRevokeAccess`: 2개 테스트
- `TestAclServiceGrantPublicAccess`: 2개 테스트
- `TestAclServiceGetDocumentAcl`: 2개 테스트
- `TestSingleton`: 5개 테스트

**총 43개 테스트, 100% PASSED**

## 기술적 특징

### 1. Permission 계층 구조
```python
# ADMIN > DELETE > WRITE > READ
Permission.ADMIN.includes(Permission.READ)   # True
Permission.READ.includes(Permission.WRITE)   # False
Permission.DELETE.includes(Permission.WRITE) # True
```

### 2. Milvus Filter 생성
```python
# 접근 가능한 문서가 있는 경우
filter = 'doc_uuid in ["uuid1", "uuid2", "uuid3"]'

# 접근 가능한 문서가 없는 경우 (아무것도 매칭하지 않음)
filter = 'doc_uuid == "__NONE__"'
```

### 3. Principal Types
- `USER`: 개별 사용자 (`user_id` 매칭)
- `GROUP`: 사용자 그룹 (`user_groups` 중 하나 매칭)
- `ORG`: 조직 (`ALL`이면 전사 공개)
- `ROLE`: 역할 기반 접근

### 4. Protocol 기반 Repository 추상화
```python
class AclRepositoryProtocol(Protocol):
    async def get_accessible_doc_uuids(...) -> list[str]: ...
    async def check_document_access(...) -> bool: ...
    # PostgresRepository에서 구현 예정
```

## 테스트 결과

```
============================== test session starts ==============================
43 passed in 0.25s

Coverage:
- src/services/acl_service.py: 93%
```

## 해결된 이슈

### 1. Ruff Lint Error
- **문제**: `UP017 Use 'datetime.UTC' alias`
- **해결**: `timezone.utc` → `UTC` (datetime에서 직접 import)

## 다음 단계
- Task 2.3.3: Entity Extraction Service 구현
- Task 2.3.4: Chunking Service 구현
