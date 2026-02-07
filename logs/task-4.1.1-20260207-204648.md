# Task 4.1.1: Document Service 구현

## 작업 정보
- **Task ID**: 4.1.1
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 20:46:48
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/26
- **Task Plan**: docs/task-plans/task-4.1.1-plan.md

## 작업 개요
문서 CRUD 비즈니스 로직을 구현합니다. 텍스트 청킹, Saga 기반 분산 트랜잭션, Kafka 이벤트 발행, ACL 권한 관리를 포함합니다.

## 생성/수정된 파일

### 1. Document Service
**파일**: `src/services/document_service.py`

#### Request/Response 모델
```python
@dataclass
class DocumentCreateRequest:
    title: str
    content: str
    owner_id: str
    owner_org: str = "default"
    source: Literal["wiki", "agit", "gdocs", "slack", "confluence", "notion", "file"] = "file"
    source_url: str | None = None
    security_level: Literal["public", "internal", "confidential"] = "internal"
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_size: int = 500
    chunk_overlap: int = 50

@dataclass
class DocumentUpdateRequest:
    title: str | None = None
    content: str | None = None
    status: Literal["draft", "published", "archived"] | None = None
    security_level: Literal["public", "internal", "confidential"] | None = None
    metadata: dict[str, Any] | None = None

@dataclass
class DocumentResponse:
    doc_uuid: str
    title: str
    owner_id: str
    owner_org: str
    source: str
    status: str
    security_level: str
    chunk_count: int
    created_at: datetime | None
    updated_at: datetime | None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### DocumentService 클래스
```python
class DocumentService:
    def __init__(
        self,
        postgres_repo: Any,
        saga_coordinator: Any,
        embedding_service: Any,
        kafka_producer: KafkaProducerProtocol | None = None,
        acl_service: Any | None = None,
    ) -> None:
        ...

    # 텍스트 청킹
    def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[str, int, int]]
    def _create_chunks(self, doc_uuid: str, version_id: str, content: str, ...) -> list[ChunkData]
    def _compute_content_hash(self, content: str) -> str

    # CRUD 작업
    async def create_document(self, request: DocumentCreateRequest) -> DocumentResponse
    async def get_document(self, doc_uuid: str, user_id: str, ...) -> DocumentResponse | None
    async def list_documents(self, user_id: str, user_groups: list[str] | None, ...) -> list[DocumentResponse]
    async def update_document(self, doc_uuid: str, request: DocumentUpdateRequest, user_id: str, ...) -> DocumentResponse
    async def delete_document(self, doc_uuid: str, user_id: str, ...) -> bool
```

### 2. 패키지 Export 업데이트
**파일**: `src/services/__init__.py`

```python
from src.services.document_service import (
    ChunkData,
    DocumentCreateRequest,
    DocumentResponse,
    DocumentService,
    DocumentUpdateRequest,
    get_document_service,
    reset_document_service,
    set_document_service,
)

__all__ = [
    ...
    # Document Service
    "ChunkData",
    "DocumentCreateRequest",
    "DocumentResponse",
    "DocumentService",
    "DocumentUpdateRequest",
    "get_document_service",
    "reset_document_service",
    "set_document_service",
    ...
]
```

### 3. Unit Tests
**파일**: `tests/unit/test_services/test_document_service.py`

#### 테스트 클래스
- **TestTextChunking** (7개 테스트)
  - 빈 텍스트 처리
  - 공백만 있는 텍스트 처리
  - 기본 청킹
  - 문장 경계 인식
  - 문단 경계 인식
  - 작은 콘텐츠 (단일 청크)
  - ChunkData 생성

- **TestCreateDocument** (5개 테스트)
  - 성공 케이스
  - 빈 콘텐츠 에러
  - 공백만 있는 콘텐츠 에러
  - Saga 실패 처리
  - 선택적 의존성 없이 동작

- **TestGetDocument** (3개 테스트)
  - 성공 케이스
  - 문서 없음
  - 접근 거부

- **TestListDocuments** (2개 테스트)
  - 성공 케이스
  - 접근 권한 없음

- **TestUpdateDocument** (4개 테스트)
  - 메타데이터만 수정
  - 콘텐츠 수정 (Saga 호출)
  - 문서 없음
  - 접근 거부

- **TestDeleteDocument** (4개 테스트)
  - 성공 케이스
  - 문서 없음
  - 접근 거부
  - Saga 실패

- **TestFactoryFunctions** (4개 테스트)
  - 의존성 필수 확인
  - 싱글톤 동작
  - set_document_service
  - reset_document_service

- **TestContentHash** (3개 테스트)
  - 해시 생성
  - 결정론적 해시
  - 다른 콘텐츠 다른 해시

**총 32개 테스트, 100% PASSED**

## 기술적 특징

### 1. 텍스트 청킹
```python
def _chunk_text(self, text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[str, int, int]]:
    # 문단/문장 경계 인식
    for sep in ["\n\n", "\n", ". ", "! ", "? ", "; "]:
        last_sep = text.rfind(sep, start, end)
        if last_sep > start + chunk_overlap:
            end = last_sep + len(sep)
            break

    # 위치 추적
    chunks.append((chunk, start, end))
```

### 2. Saga 연동
```python
# 문서 생성
result = await self._saga.execute_create_saga(doc_obj, chunk_objs)

# 문서 업데이트 (콘텐츠 변경 시)
result = await self._saga.execute_update_saga(doc_uuid, doc_obj, chunk_objs)

# 문서 삭제
result = await self._saga.execute_delete_saga(doc_uuid)
```

### 3. ACL 권한 검증
```python
# 읽기 권한
has_access = await self._acl.check_access(user_id, user_groups, doc_uuid, Permission.READ)

# 쓰기 권한
has_access = await self._acl.check_access(user_id, user_groups, doc_uuid, Permission.WRITE)

# 관리자 권한 (삭제용)
has_access = await self._acl.check_access(user_id, user_groups, doc_uuid, Permission.ADMIN)
```

### 4. Kafka 이벤트 발행
```python
# 문서 생성
await self._kafka.send("document.created", {...})

# 문서 수정
await self._kafka.send("document.updated", {...})

# 문서 삭제
await self._kafka.send("document.deleted", {...})
```

### 5. 콘텐츠 해시
```python
def _compute_content_hash(self, content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
```

## 테스트 결과

```
============================== test session starts ==============================
32 passed in 0.42s

테스트 분류:
- TestTextChunking: 7개
- TestCreateDocument: 5개
- TestGetDocument: 3개
- TestListDocuments: 2개
- TestUpdateDocument: 4개
- TestDeleteDocument: 4개
- TestFactoryFunctions: 4개
- TestContentHash: 3개

커버리지: src/services/document_service.py - 94%
```

## 워크플로우

### 문서 생성 플로우
```
1. 콘텐츠 검증 (비어있지 않은지)
2. UUID 생성 (doc_uuid, version_id)
3. 텍스트 청킹 (문장/문단 경계 인식)
4. 콘텐츠 해시 계산 (SHA-256)
5. Saga 실행 (PostgreSQL → Milvus → Neo4j)
6. 소유자 ACL 권한 부여
7. Kafka 이벤트 발행
8. DocumentResponse 반환
```

### 문서 업데이트 플로우
```
1. 쓰기 권한 검증
2. 기존 문서 조회
3. 메타데이터만 변경?
   - Yes: PostgreSQL만 업데이트
   - No: 새 청크 생성 + Update Saga 실행
4. Kafka 이벤트 발행
5. DocumentResponse 반환
```

### 문서 삭제 플로우
```
1. 관리자 권한 검증
2. 문서 존재 확인
3. Delete Saga 실행 (Neo4j → Milvus → PostgreSQL)
4. Kafka 이벤트 발행
5. True 반환
```

## API 사용 예시

### 문서 생성
```python
from src.services.document_service import get_document_service, DocumentCreateRequest

service = get_document_service(postgres_repo, saga, embedding)

request = DocumentCreateRequest(
    title="인공지능 개요",
    content="인공지능(AI)은 기계가 인간의 지능을 모방하는 기술입니다...",
    owner_id="user1",
    owner_org="engineering",
    chunk_size=500,
)

response = await service.create_document(request)
print(f"Created: {response.doc_uuid}, Chunks: {response.chunk_count}")
```

### 문서 조회
```python
doc = await service.get_document(
    doc_uuid="doc-123",
    user_id="user1",
    user_groups=["engineering"],
)
```

### 문서 수정
```python
from src.services.document_service import DocumentUpdateRequest

update = DocumentUpdateRequest(
    title="인공지능 개요 (수정판)",
    content="새로운 내용...",  # 콘텐츠 변경 시 Saga 실행
)

updated = await service.update_document("doc-123", update, "user1")
```

### 문서 삭제
```python
result = await service.delete_document("doc-123", "user1")
```

## 다음 단계
- Task 4.1.2: Document API Router 구현
- Task 4.2: Document 통합 테스트
