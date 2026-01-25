# Task Execution Plan: 4.2.4 - FastAPI 애플리케이션 통합

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.4 |
| **Task Name** | FastAPI 애플리케이션 통합 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 4.1.2, Task 3.2.1, Task 4.2.2 |

### Description
모든 Router를 통합하고 FastAPI 애플리케이션을 완성합니다.

### Acceptance Criteria
- [ ] `src/main.py` 완성
- [ ] 모든 Router 등록 (/documents, /search, /health, /metrics)
- [ ] 의존성 주입 설정 (`dependencies.py`)
- [ ] Lifespan 이벤트 (startup: DB 연결, shutdown: DB 종료)
- [ ] CORS 설정
- [ ] 예외 핸들러 등록

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.1 API Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.1 Web Framework

### 2.2 애플리케이션 구조
```
src/
├── main.py                 # FastAPI 앱 정의
├── config.py               # 설정
├── api/
│   ├── __init__.py
│   ├── dependencies.py     # 의존성 주입
│   ├── exception_handlers.py  # 예외 핸들러
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── audit.py
│   │   └── metrics.py
│   └── routers/
│       ├── __init__.py
│       ├── documents.py
│       ├── search.py
│       ├── health.py
│       └── metrics.py
└── ...
```

### 2.3 Lifespan 이벤트
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_databases()
    await start_services()
    yield
    # Shutdown
    await stop_services()
    await disconnect_databases()
```

### 2.4 설계 결정
1. **Lifespan**: asynccontextmanager 사용
2. **CORS**: 개발 환경 * 허용, 프로덕션 제한
3. **예외 핸들러**: 커스텀 에러 응답
4. **미들웨어**: 순서 중요 (외부 → 내부)

---

## 3. Implementation Steps

### Step 1: 예외 핸들러 구현 (1h)

**작업 내용:**
1. 커스텀 예외 정의
2. 전역 예외 핸들러
3. 에러 응답 스키마

**src/api/exceptions.py:**
```python
"""Custom exceptions."""
from typing import Any


class KnowledgeStoreError(Exception):
    """Base exception for Knowledge Store."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class NotFoundError(KnowledgeStoreError):
    """Resource not found."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} not found: {resource_id}",
            error_code="NOT_FOUND",
            details={"resource": resource, "resource_id": resource_id},
        )


class AccessDeniedError(KnowledgeStoreError):
    """Access denied."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            error_code="ACCESS_DENIED",
        )


class ValidationError(KnowledgeStoreError):
    """Validation error."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details={"field": field} if field else {},
        )


class ServiceUnavailableError(KnowledgeStoreError):
    """Service unavailable."""

    def __init__(self, service: str):
        super().__init__(
            message=f"Service unavailable: {service}",
            error_code="SERVICE_UNAVAILABLE",
            details={"service": service},
        )
```

**src/api/exception_handlers.py:**
```python
"""Exception handlers for FastAPI."""
import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.exceptions import (
    AccessDeniedError,
    KnowledgeStoreError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Error response schema."""

    error: str
    message: str
    error_code: str | None = None
    details: dict[str, Any] = {}


def create_error_response(
    status_code: int,
    error: str,
    message: str,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Create error JSON response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=error,
            message=message,
            error_code=error_code,
            details=details or {},
        ).model_dump(),
    )


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    """Handle NotFoundError."""
    logger.warning(f"Not found: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        error="Not Found",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def access_denied_handler(request: Request, exc: AccessDeniedError) -> JSONResponse:
    """Handle AccessDeniedError."""
    logger.warning(f"Access denied: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        error="Forbidden",
        message=exc.message,
        error_code=exc.error_code,
    )


async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle ValidationError."""
    return create_error_response(
        status_code=status.HTTP_400_BAD_REQUEST,
        error="Bad Request",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def service_unavailable_handler(
    request: Request,
    exc: ServiceUnavailableError,
) -> JSONResponse:
    """Handle ServiceUnavailableError."""
    logger.error(f"Service unavailable: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        error="Service Unavailable",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def generic_error_handler(request: Request, exc: KnowledgeStoreError) -> JSONResponse:
    """Handle generic KnowledgeStoreError."""
    logger.error(f"Error: {exc.message}")
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        message=exc.message,
        error_code=exc.error_code,
        details=exc.details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions."""
    logger.exception(f"Unhandled exception: {exc}")
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error="Internal Server Error",
        message="An unexpected error occurred",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers."""
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(AccessDeniedError, access_denied_handler)
    app.add_exception_handler(ValidationError, validation_handler)
    app.add_exception_handler(ServiceUnavailableError, service_unavailable_handler)
    app.add_exception_handler(KnowledgeStoreError, generic_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
```

**완료 기준:**
- [ ] 커스텀 예외 클래스
- [ ] 예외 핸들러 구현
- [ ] 에러 응답 스키마

---

### Step 2: 의존성 주입 및 Lifespan (1.5h)

**작업 내용:**
1. 의존성 주입 설정
2. Lifespan 이벤트
3. 클라이언트 초기화

**src/api/dependencies.py:**
```python
"""API dependencies and service factories."""
import logging
from typing import Any

from src.config import get_settings
from src.infrastructure.database.postgres import PostgresClient, get_postgres_client
from src.infrastructure.database.milvus import MilvusClient, get_milvus_client
from src.infrastructure.database.neo4j import Neo4jClient, get_neo4j_client
from src.infrastructure.messaging.kafka import KafkaProducer, get_kafka_producer
from src.infrastructure.embedding.bge_m3 import EmbeddingService, get_embedding_service
from src.repositories.postgres.repository import PostgresRepository
from src.repositories.milvus.repository import MilvusRepository
from src.repositories.neo4j.repository import Neo4jRepository
from src.services.document_service import DocumentService
from src.services.search_service import SearchService
from src.services.acl_service import AclService
from src.services.saga.coordinator import SagaCoordinator
from src.services.audit_service import AuditService

logger = logging.getLogger(__name__)

# Clients
_postgres_client: PostgresClient | None = None
_milvus_client: MilvusClient | None = None
_neo4j_client: Neo4jClient | None = None
_kafka_producer: KafkaProducer | None = None
_embedding_service: EmbeddingService | None = None

# Services
_document_service: DocumentService | None = None
_search_service: SearchService | None = None
_acl_service: AclService | None = None
_audit_service: AuditService | None = None


async def init_clients() -> None:
    """Initialize all database clients."""
    global _postgres_client, _milvus_client, _neo4j_client
    global _kafka_producer, _embedding_service

    settings = get_settings()

    logger.info("Initializing clients...")

    # PostgreSQL
    _postgres_client = get_postgres_client(settings.postgres)
    await _postgres_client.connect()
    logger.info("PostgreSQL connected")

    # Milvus
    _milvus_client = get_milvus_client(settings.milvus)
    await _milvus_client.connect()
    logger.info("Milvus connected")

    # Neo4j
    _neo4j_client = get_neo4j_client(settings.neo4j)
    await _neo4j_client.connect()
    logger.info("Neo4j connected")

    # Kafka
    _kafka_producer = get_kafka_producer(settings.kafka)
    await _kafka_producer.start()
    logger.info("Kafka producer started")

    # Embedding service (lazy load)
    _embedding_service = get_embedding_service()
    logger.info("Embedding service ready")


async def init_services() -> None:
    """Initialize all services."""
    global _document_service, _search_service, _acl_service, _audit_service

    logger.info("Initializing services...")

    # Repositories
    postgres_repo = PostgresRepository(_postgres_client)
    milvus_repo = MilvusRepository(_milvus_client)
    neo4j_repo = Neo4jRepository(_neo4j_client)

    # ACL Service
    _acl_service = AclService(postgres_repo)

    # Saga Coordinator
    saga = SagaCoordinator(
        postgres_repo=postgres_repo,
        milvus_repo=milvus_repo,
        neo4j_repo=neo4j_repo,
        embedding_service=_embedding_service,
    )

    # Document Service
    _document_service = DocumentService(
        postgres_repo=postgres_repo,
        saga_coordinator=saga,
        embedding_service=_embedding_service,
        kafka_producer=_kafka_producer,
        acl_service=_acl_service,
    )

    # Search Service
    _search_service = SearchService(
        milvus_repo=milvus_repo,
        embedding_service=_embedding_service,
        acl_service=_acl_service,
        neo4j_repo=neo4j_repo,
    )

    # Audit Service
    _audit_service = AuditService(postgres_repo)
    await _audit_service.start()

    logger.info("All services initialized")


async def close_clients() -> None:
    """Close all database clients."""
    global _postgres_client, _milvus_client, _neo4j_client
    global _kafka_producer, _audit_service

    logger.info("Closing clients...")

    if _audit_service:
        await _audit_service.stop()

    if _kafka_producer:
        await _kafka_producer.stop()

    if _neo4j_client:
        await _neo4j_client.close()

    if _milvus_client:
        await _milvus_client.close()

    if _postgres_client:
        await _postgres_client.close()

    logger.info("All clients closed")


# Dependency getters
async def get_document_service() -> DocumentService:
    """Get document service."""
    if _document_service is None:
        raise RuntimeError("Document service not initialized")
    return _document_service


async def get_search_service() -> SearchService:
    """Get search service."""
    if _search_service is None:
        raise RuntimeError("Search service not initialized")
    return _search_service


async def get_acl_service() -> AclService:
    """Get ACL service."""
    if _acl_service is None:
        raise RuntimeError("ACL service not initialized")
    return _acl_service


async def get_audit_service() -> AuditService:
    """Get audit service."""
    if _audit_service is None:
        raise RuntimeError("Audit service not initialized")
    return _audit_service


def get_clients_for_health() -> dict[str, Any]:
    """Get client references for health checks."""
    return {
        "postgres": _postgres_client,
        "milvus": _milvus_client,
        "neo4j": _neo4j_client,
        "kafka": _kafka_producer,
    }
```

**완료 기준:**
- [ ] init_clients 함수
- [ ] init_services 함수
- [ ] close_clients 함수
- [ ] 의존성 getter 함수

---

### Step 3: main.py 완성 (1h)

**작업 내용:**
1. FastAPI 앱 정의
2. Router 등록
3. Middleware 등록
4. CORS 설정

**src/main.py:**
```python
"""FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api.dependencies import (
    close_clients,
    get_clients_for_health,
    get_document_service,
    get_search_service,
    init_clients,
    init_services,
)
from src.api.exception_handlers import register_exception_handlers
from src.api.middleware.audit import AuditContextMiddleware
from src.api.middleware.metrics import MetricsMiddleware
from src.api.routers import documents, search, health, metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting application...")

    try:
        await init_clients()
        await init_services()

        # Set health check clients
        from src.api.routers.health import set_clients
        set_clients(**get_clients_for_health())

        logger.info("Application started successfully")
        yield

    finally:
        # Shutdown
        logger.info("Shutting down application...")
        await close_clients()
        logger.info("Application shut down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Knowledge Store API",
        description="Knowledge Store Layer for enterprise document management and search",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters: outer -> inner)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(AuditContextMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(documents.router, prefix="/api/v1")
    app.include_router(search.router, prefix="/api/v1")
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(metrics.router, prefix="/api/v1")

    # Override dependencies
    app.dependency_overrides[documents.get_document_service] = get_document_service
    app.dependency_overrides[search.get_search_service] = get_search_service

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "Knowledge Store API",
            "version": "1.0.0",
            "docs": "/api/docs",
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
```

**완료 기준:**
- [ ] Lifespan 핸들러
- [ ] create_app 함수
- [ ] Router 등록
- [ ] Middleware 등록
- [ ] CORS 설정

---

### Step 4: 테스트 작성 (0.5h)

**작업 내용:**
1. 앱 시작/종료 테스트
2. 라우터 등록 테스트

**tests/unit/test_app.py:**
```python
"""Tests for FastAPI application."""
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestApp:
    """Tests for application."""

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    def test_app_starts(
        self,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test app starts successfully."""
        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/")

            assert response.status_code == 200
            assert "Knowledge Store" in response.json()["name"]

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    def test_routers_registered(
        self,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test all routers are registered."""
        from src.main import create_app

        app = create_app()

        # Check routes exist
        routes = [route.path for route in app.routes]

        assert "/api/v1/documents" in routes or any("/documents" in r for r in routes)
        assert "/api/v1/search" in routes or any("/search" in r for r in routes)
        assert "/api/v1/health" in routes or any("/health" in r for r in routes)
        assert "/api/v1/metrics" in routes or any("/metrics" in r for r in routes)

    @patch("src.api.dependencies.init_clients", new_callable=AsyncMock)
    @patch("src.api.dependencies.init_services", new_callable=AsyncMock)
    @patch("src.api.dependencies.close_clients", new_callable=AsyncMock)
    def test_openapi_docs(
        self,
        mock_close: AsyncMock,
        mock_init_services: AsyncMock,
        mock_init_clients: AsyncMock,
    ) -> None:
        """Test OpenAPI docs are available."""
        from src.main import create_app

        app = create_app()

        with TestClient(app) as client:
            response = client.get("/api/openapi.json")

            assert response.status_code == 200
            assert "openapi" in response.json()
```

**완료 기준:**
- [ ] 앱 시작 테스트
- [ ] 라우터 등록 테스트
- [ ] OpenAPI 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_app_starts` | 앱 시작 | 성공 |
| `test_routers_registered` | 라우터 등록 | 모든 라우터 |
| `test_openapi_docs` | OpenAPI | JSON 반환 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 초기화 순서 | High | Low | 명시적 순서 문서화 |
| 메모리 누수 | Medium | Low | 종료 시 정리 확인 |

---

## 6. Definition of Done

- [ ] `src/main.py` 완성
- [ ] 모든 Router 등록
- [ ] 의존성 주입 설정
- [ ] Lifespan 이벤트
- [ ] CORS 설정
- [ ] 예외 핸들러
- [ ] 테스트 작성 및 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 예외 핸들러 | 1h | - |
| Step 2: 의존성/Lifespan | 1.5h | - |
| Step 3: main.py | 1h | - |
| Step 4: 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
