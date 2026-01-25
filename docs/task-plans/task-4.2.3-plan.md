# Task Execution Plan: 4.2.3 - Audit Logger 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.3 |
| **Task Name** | Audit Logger 구현 |
| **Estimate** | 4h |
| **Priority** | P1 |
| **Dependencies** | Task 2.2.1 |

### Description
모든 조회/수정 이력을 기록하는 Audit Logger를 구현합니다.

### Acceptance Criteria
- [ ] `src/services/audit_service.py` 생성
- [ ] 검색 요청 로깅 (user_id, query, retrieved_docs)
- [ ] 문서 접근 로깅 (user_id, doc_uuid, action)
- [ ] 비동기 로깅 (성능 영향 최소화)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.7 Audit
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 6 NFR-5

### 2.2 Audit 요구사항
```
감사 대상:
1. 검색 요청: 누가, 무엇을, 언제, 어떤 결과
2. 문서 접근: 누가, 어떤 문서, 어떤 작업
3. 권한 변경: 누가, 어떤 문서, 어떤 권한

감사 필드:
- user_id: 사용자 ID
- action: 수행한 작업
- resource_type: 리소스 타입 (document, search)
- resource_id: 리소스 ID
- query_text: 검색어 (검색 시)
- retrieved_docs: 조회된 문서 목록
- timestamp: 발생 시간
- ip_address: 클라이언트 IP (선택)
```

### 2.3 설계 결정
1. **비동기 저장**: 메인 흐름 차단 안함
2. **배치 저장**: 일정 주기로 배치 삽입
3. **PostgreSQL 저장**: audit_logs 테이블
4. **보존 정책**: 90일 보관 (설정 가능)

### 2.4 데이터 모델
```sql
-- audit_logs 테이블
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(100),
    query_text TEXT,
    retrieved_docs TEXT[],
    metadata JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_created_at ON audit_logs(created_at);
CREATE INDEX idx_audit_action ON audit_logs(action);
```

---

## 3. Implementation Steps

### Step 1: Audit 모델 정의 (1h)

**작업 내용:**
1. AuditLog 도메인 모델
2. AuditAction 열거형
3. 로깅 인터페이스

**src/domain/models/audit.py:**
```python
"""Audit domain models."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuditAction(str, Enum):
    """Audit action types."""

    # Search actions
    SEARCH = "search"
    SEARCH_DENSE = "search_dense"
    SEARCH_SPARSE = "search_sparse"
    SEARCH_GRAPH = "search_graph"
    SEARCH_HYBRID = "search_hybrid"

    # Document actions
    DOCUMENT_CREATE = "document_create"
    DOCUMENT_READ = "document_read"
    DOCUMENT_UPDATE = "document_update"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_LIST = "document_list"

    # Permission actions
    PERMISSION_GRANT = "permission_grant"
    PERMISSION_REVOKE = "permission_revoke"
    PERMISSION_CHECK = "permission_check"


class ResourceType(str, Enum):
    """Resource types."""

    DOCUMENT = "document"
    SEARCH = "search"
    PERMISSION = "permission"


@dataclass
class AuditLog:
    """Audit log entry."""

    user_id: str
    action: AuditAction
    resource_type: ResourceType
    resource_id: str | None = None
    query_text: str | None = None
    retrieved_docs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "user_id": self.user_id,
            "action": self.action.value,
            "resource_type": self.resource_type.value,
            "resource_id": self.resource_id,
            "query_text": self.query_text,
            "retrieved_docs": self.retrieved_docs,
            "metadata": self.metadata,
            "ip_address": self.ip_address,
            "created_at": self.created_at,
        }


@dataclass
class AuditQuery:
    """Query parameters for audit logs."""

    user_id: str | None = None
    action: AuditAction | None = None
    resource_type: ResourceType | None = None
    resource_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0
```

**완료 기준:**
- [ ] AuditAction 열거형
- [ ] ResourceType 열거형
- [ ] AuditLog 모델
- [ ] AuditQuery 모델

---

### Step 2: Audit Service 구현 (1.5h)

**작업 내용:**
1. AuditService 클래스
2. 비동기 로깅
3. 배치 저장

**src/services/audit_service.py:**
```python
"""Audit service for logging user actions."""
import asyncio
import logging
from collections import deque
from typing import Any, Protocol

from src.domain.models.audit import (
    AuditAction,
    AuditLog,
    AuditQuery,
    ResourceType,
)

logger = logging.getLogger(__name__)


class AuditRepositoryProtocol(Protocol):
    """Protocol for audit repository."""

    async def create_audit_log(self, log: AuditLog) -> AuditLog:
        """Create single audit log."""
        ...

    async def create_audit_logs_batch(self, logs: list[AuditLog]) -> int:
        """Create multiple audit logs."""
        ...

    async def query_audit_logs(self, query: AuditQuery) -> list[AuditLog]:
        """Query audit logs."""
        ...


class AuditService:
    """Service for audit logging."""

    def __init__(
        self,
        repository: AuditRepositoryProtocol,
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
    ) -> None:
        """Initialize audit service.

        Args:
            repository: Audit repository
            batch_size: Number of logs to batch before flush
            flush_interval_seconds: Max time between flushes
        """
        self._repository = repository
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._buffer: deque[AuditLog] = deque()
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start background flush task."""
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._periodic_flush())
            logger.info("Audit service started")

    async def stop(self) -> None:
        """Stop and flush remaining logs."""
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush remaining
        await self._flush()
        logger.info("Audit service stopped")

    async def _periodic_flush(self) -> None:
        """Periodically flush buffer."""
        while True:
            await asyncio.sleep(self._flush_interval)
            await self._flush()

    async def _flush(self) -> None:
        """Flush buffer to database."""
        async with self._lock:
            if not self._buffer:
                return

            logs = list(self._buffer)
            self._buffer.clear()

        try:
            count = await self._repository.create_audit_logs_batch(logs)
            logger.debug(f"Flushed {count} audit logs")
        except Exception as e:
            logger.error(f"Failed to flush audit logs: {e}")
            # Put back in buffer for retry
            async with self._lock:
                self._buffer.extendleft(logs)

    async def _add_log(self, log: AuditLog) -> None:
        """Add log to buffer."""
        async with self._lock:
            self._buffer.append(log)

            if len(self._buffer) >= self._batch_size:
                # Trigger flush
                asyncio.create_task(self._flush())

    async def log_search(
        self,
        user_id: str,
        query: str,
        retrieved_docs: list[str],
        search_type: str = "hybrid",
        duration_ms: float | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Log search request.

        Args:
            user_id: User who performed search
            query: Search query
            retrieved_docs: List of retrieved document UUIDs
            search_type: Type of search performed
            duration_ms: Search duration in milliseconds
            ip_address: Client IP address
        """
        action_map = {
            "dense": AuditAction.SEARCH_DENSE,
            "sparse": AuditAction.SEARCH_SPARSE,
            "graph": AuditAction.SEARCH_GRAPH,
            "hybrid": AuditAction.SEARCH_HYBRID,
        }

        log = AuditLog(
            user_id=user_id,
            action=action_map.get(search_type, AuditAction.SEARCH),
            resource_type=ResourceType.SEARCH,
            query_text=query,
            retrieved_docs=retrieved_docs,
            metadata={"duration_ms": duration_ms} if duration_ms else {},
            ip_address=ip_address,
        )

        await self._add_log(log)

    async def log_document_access(
        self,
        user_id: str,
        doc_uuid: str,
        action: AuditAction,
        ip_address: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log document access.

        Args:
            user_id: User who accessed document
            doc_uuid: Document UUID
            action: Action performed
            ip_address: Client IP address
            metadata: Additional metadata
        """
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=ResourceType.DOCUMENT,
            resource_id=doc_uuid,
            metadata=metadata or {},
            ip_address=ip_address,
        )

        await self._add_log(log)

    async def log_permission_change(
        self,
        user_id: str,
        doc_uuid: str,
        action: AuditAction,
        principal_type: str,
        principal_id: str,
        permission: str,
        ip_address: str | None = None,
    ) -> None:
        """Log permission change.

        Args:
            user_id: User who changed permission
            doc_uuid: Document UUID
            action: Action (grant or revoke)
            principal_type: Type of principal
            principal_id: Principal ID
            permission: Permission level
            ip_address: Client IP address
        """
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=ResourceType.PERMISSION,
            resource_id=doc_uuid,
            metadata={
                "principal_type": principal_type,
                "principal_id": principal_id,
                "permission": permission,
            },
            ip_address=ip_address,
        )

        await self._add_log(log)

    async def query_logs(self, query: AuditQuery) -> list[AuditLog]:
        """Query audit logs.

        Args:
            query: Query parameters

        Returns:
            List of matching audit logs
        """
        return await self._repository.query_audit_logs(query)
```

**완료 기준:**
- [ ] AuditService 클래스
- [ ] 비동기 배치 저장
- [ ] log_search 메서드
- [ ] log_document_access 메서드
- [ ] log_permission_change 메서드

---

### Step 3: Middleware 및 통합 (1h)

**작업 내용:**
1. 요청 컨텍스트에서 IP 추출
2. 서비스 통합 헬퍼

**src/api/middleware/audit.py:**
```python
"""Audit middleware."""
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request."""
    # Check X-Forwarded-For header (for proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # First IP in the list is the client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


class AuditContextMiddleware(BaseHTTPMiddleware):
    """Middleware to add audit context to request state."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ):
        """Add client IP to request state."""
        request.state.client_ip = get_client_ip(request)
        return await call_next(request)
```

**src/services/audit_integration.py:**
```python
"""Audit integration helpers."""
from typing import Any

from src.domain.models.audit import AuditAction
from src.services.audit_service import AuditService

# Global audit service instance
_audit_service: AuditService | None = None


def set_audit_service(service: AuditService) -> None:
    """Set global audit service."""
    global _audit_service
    _audit_service = service


def get_audit_service() -> AuditService | None:
    """Get global audit service."""
    return _audit_service


async def audit_search(
    user_id: str,
    query: str,
    retrieved_docs: list[str],
    search_type: str = "hybrid",
    duration_ms: float | None = None,
    ip_address: str | None = None,
) -> None:
    """Log search if audit service is available."""
    if _audit_service:
        await _audit_service.log_search(
            user_id=user_id,
            query=query,
            retrieved_docs=retrieved_docs,
            search_type=search_type,
            duration_ms=duration_ms,
            ip_address=ip_address,
        )


async def audit_document(
    user_id: str,
    doc_uuid: str,
    action: AuditAction,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log document access if audit service is available."""
    if _audit_service:
        await _audit_service.log_document_access(
            user_id=user_id,
            doc_uuid=doc_uuid,
            action=action,
            ip_address=ip_address,
            metadata=metadata,
        )
```

**완료 기준:**
- [ ] IP 추출 미들웨어
- [ ] 통합 헬퍼 함수

---

### Step 4: 테스트 작성 (0.5h)

**작업 내용:**
1. AuditService 테스트
2. 배치 저장 테스트

**tests/unit/test_services/test_audit_service.py:**
```python
"""Tests for audit service."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.audit_service import AuditService
from src.domain.models.audit import AuditAction, AuditLog


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create mock repository."""
    mock = MagicMock()
    mock.create_audit_logs_batch = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def audit_service(mock_repository: MagicMock) -> AuditService:
    """Create audit service."""
    return AuditService(
        repository=mock_repository,
        batch_size=10,
        flush_interval_seconds=1.0,
    )


class TestAuditService:
    """Tests for AuditService."""

    async def test_log_search(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test search logging."""
        await audit_service.log_search(
            user_id="user1",
            query="test query",
            retrieved_docs=["doc1", "doc2"],
            search_type="hybrid",
        )

        # Force flush
        await audit_service._flush()

        mock_repository.create_audit_logs_batch.assert_called_once()
        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert len(logs) == 1
        assert logs[0].user_id == "user1"
        assert logs[0].query_text == "test query"

    async def test_batch_flush(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test batch flushing when buffer is full."""
        # Set small batch size
        audit_service._batch_size = 2

        await audit_service.log_search("user1", "q1", [])
        await audit_service.log_search("user1", "q2", [])

        # Wait for async flush
        await asyncio.sleep(0.1)

        mock_repository.create_audit_logs_batch.assert_called()

    async def test_log_document_access(
        self,
        audit_service: AuditService,
        mock_repository: MagicMock,
    ) -> None:
        """Test document access logging."""
        await audit_service.log_document_access(
            user_id="user1",
            doc_uuid="doc-123",
            action=AuditAction.DOCUMENT_READ,
        )

        await audit_service._flush()

        logs = mock_repository.create_audit_logs_batch.call_args[0][0]
        assert logs[0].action == AuditAction.DOCUMENT_READ
        assert logs[0].resource_id == "doc-123"
```

**완료 기준:**
- [ ] 검색 로깅 테스트
- [ ] 배치 저장 테스트
- [ ] 문서 접근 로깅 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_log_search` | 검색 로깅 | 로그 저장 |
| `test_batch_flush` | 배치 저장 | 임계점 초과 시 flush |
| `test_log_document` | 문서 접근 | 로그 저장 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 로깅 성능 영향 | Medium | Medium | 비동기, 배치 처리 |
| 버퍼 오버플로우 | Low | Low | 최대 크기 제한 |

---

## 6. Definition of Done

- [ ] `src/services/audit_service.py` 구현
- [ ] AuditLog 모델 정의
- [ ] 비동기 배치 저장
- [ ] 검색/문서/권한 로깅
- [ ] 테스트 작성 및 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 모델 정의 | 1h | - |
| Step 2: Audit Service | 1.5h | - |
| Step 3: 통합 | 1h | - |
| Step 4: 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
