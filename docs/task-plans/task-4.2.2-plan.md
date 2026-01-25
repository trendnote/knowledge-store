# Task Execution Plan: 4.2.2 - Health Check 및 Metrics 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.2 |
| **Task Name** | Health Check 및 Metrics 구현 |
| **Estimate** | 4h |
| **Priority** | P1 |
| **Dependencies** | Task 2.1.1, 2.1.2, 2.1.3, 2.1.4 |

### Description
Health Check 및 Prometheus Metrics 엔드포인트를 구현합니다.

### Acceptance Criteria
- [ ] `src/api/routers/health.py` 생성
- [ ] `src/api/routers/metrics.py` 생성
- [ ] `GET /api/v1/health`: 각 저장소 연결 상태 확인
- [ ] `GET /api/v1/metrics`: Prometheus 메트릭 노출
- [ ] 메트릭: 요청 수, 응답 시간, 에러 수

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.5 Monitoring
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 6 NFR-4

### 2.2 Health Check 설계
```json
GET /api/v1/health

Response:
{
    "status": "healthy",  // or "unhealthy"
    "timestamp": "2026-01-26T10:00:00Z",
    "checks": {
        "postgres": {"status": "up", "latency_ms": 5},
        "milvus": {"status": "up", "latency_ms": 10},
        "neo4j": {"status": "up", "latency_ms": 8},
        "kafka": {"status": "up", "latency_ms": 3}
    }
}
```

### 2.3 Prometheus 메트릭
```
# Request metrics
knowledge_store_requests_total{method="POST", endpoint="/documents", status="200"}
knowledge_store_request_duration_seconds{method="GET", endpoint="/search"}

# Error metrics
knowledge_store_errors_total{type="database", component="postgres"}

# Business metrics
knowledge_store_documents_total
knowledge_store_chunks_total
knowledge_store_searches_total
```

### 2.4 설계 결정
1. **prometheus-fastapi-instrumentator**: FastAPI 자동 계측
2. **커스텀 메트릭**: 비즈니스 메트릭 추가
3. **Health Check 캐싱**: 1초 캐싱으로 부하 방지

---

## 3. Implementation Steps

### Step 1: Health Check Router 구현 (1.5h)

**작업 내용:**
1. Health check 엔드포인트
2. 각 저장소 ping
3. 결과 집계

**src/api/routers/health.py:**
```python
"""Health check router."""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class CheckResult(BaseModel):
    """Single check result."""

    status: str  # "up" or "down"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "healthy" or "unhealthy"
    timestamp: datetime
    checks: dict[str, CheckResult]


# Client references (set during app startup)
_postgres_client: Any = None
_milvus_client: Any = None
_neo4j_client: Any = None
_kafka_producer: Any = None


def set_clients(
    postgres: Any = None,
    milvus: Any = None,
    neo4j: Any = None,
    kafka: Any = None,
) -> None:
    """Set client references for health checks."""
    global _postgres_client, _milvus_client, _neo4j_client, _kafka_producer
    _postgres_client = postgres
    _milvus_client = milvus
    _neo4j_client = neo4j
    _kafka_producer = kafka


async def _check_postgres() -> CheckResult:
    """Check PostgreSQL connection."""
    if _postgres_client is None:
        return CheckResult(status="down", error="Client not configured")

    start = time.time()
    try:
        is_ok = await _postgres_client.ping()
        latency = (time.time() - start) * 1000
        return CheckResult(
            status="up" if is_ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return CheckResult(status="down", error=str(e))


async def _check_milvus() -> CheckResult:
    """Check Milvus connection."""
    if _milvus_client is None:
        return CheckResult(status="down", error="Client not configured")

    start = time.time()
    try:
        is_ok = await _milvus_client.ping()
        latency = (time.time() - start) * 1000
        return CheckResult(
            status="up" if is_ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return CheckResult(status="down", error=str(e))


async def _check_neo4j() -> CheckResult:
    """Check Neo4j connection."""
    if _neo4j_client is None:
        return CheckResult(status="down", error="Client not configured")

    start = time.time()
    try:
        is_ok = await _neo4j_client.ping()
        latency = (time.time() - start) * 1000
        return CheckResult(
            status="up" if is_ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return CheckResult(status="down", error=str(e))


async def _check_kafka() -> CheckResult:
    """Check Kafka connection."""
    if _kafka_producer is None:
        return CheckResult(status="down", error="Client not configured")

    start = time.time()
    try:
        is_ok = await _kafka_producer.ping()
        latency = (time.time() - start) * 1000
        return CheckResult(
            status="up" if is_ok else "down",
            latency_ms=round(latency, 2),
        )
    except Exception as e:
        return CheckResult(status="down", error=str(e))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check health of all system components.",
)
async def health_check() -> HealthResponse:
    """Check system health."""
    # Run all checks in parallel
    results = await asyncio.gather(
        _check_postgres(),
        _check_milvus(),
        _check_neo4j(),
        _check_kafka(),
        return_exceptions=True,
    )

    checks = {
        "postgres": results[0] if not isinstance(results[0], Exception) else CheckResult(status="down", error=str(results[0])),
        "milvus": results[1] if not isinstance(results[1], Exception) else CheckResult(status="down", error=str(results[1])),
        "neo4j": results[2] if not isinstance(results[2], Exception) else CheckResult(status="down", error=str(results[2])),
        "kafka": results[3] if not isinstance(results[3], Exception) else CheckResult(status="down", error=str(results[3])),
    }

    # Overall status: healthy only if all are up
    all_up = all(c.status == "up" for c in checks.values())

    return HealthResponse(
        status="healthy" if all_up else "unhealthy",
        timestamp=datetime.utcnow(),
        checks=checks,
    )


@router.get(
    "/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Simple liveness check for Kubernetes.",
)
async def liveness() -> dict:
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get(
    "/health/ready",
    summary="Readiness Probe",
    description="Readiness check for Kubernetes.",
)
async def readiness() -> dict:
    """Kubernetes readiness probe."""
    health = await health_check()

    if health.status != "healthy":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready",
        )

    return {"status": "ready"}
```

**완료 기준:**
- [ ] /health 엔드포인트
- [ ] /health/live 엔드포인트
- [ ] /health/ready 엔드포인트
- [ ] 병렬 체크

---

### Step 2: Prometheus Metrics 설정 (1.5h)

**작업 내용:**
1. prometheus-fastapi-instrumentator 설정
2. 커스텀 메트릭 정의
3. 메트릭 엔드포인트

**src/api/routers/metrics.py:**
```python
"""Prometheus metrics router."""
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import APIRouter, Response

router = APIRouter(tags=["metrics"])

# Request metrics
REQUEST_COUNT = Counter(
    "knowledge_store_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "knowledge_store_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# Error metrics
ERROR_COUNT = Counter(
    "knowledge_store_errors_total",
    "Total number of errors",
    ["type", "component"],
)

# Business metrics
DOCUMENTS_TOTAL = Gauge(
    "knowledge_store_documents_total",
    "Total number of documents",
)

CHUNKS_TOTAL = Gauge(
    "knowledge_store_chunks_total",
    "Total number of chunks",
)

SEARCHES_TOTAL = Counter(
    "knowledge_store_searches_total",
    "Total number of searches",
    ["search_type"],
)

SEARCH_LATENCY = Histogram(
    "knowledge_store_search_duration_seconds",
    "Search latency in seconds",
    ["search_type"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

# Database metrics
DB_CONNECTION_POOL_SIZE = Gauge(
    "knowledge_store_db_pool_size",
    "Database connection pool size",
    ["database"],
)

DB_CONNECTION_POOL_USED = Gauge(
    "knowledge_store_db_pool_used",
    "Database connections in use",
    ["database"],
)


def record_request(method: str, endpoint: str, status: int, duration: float) -> None:
    """Record request metrics."""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


def record_error(error_type: str, component: str) -> None:
    """Record error metrics."""
    ERROR_COUNT.labels(type=error_type, component=component).inc()


def record_search(search_type: str, duration: float) -> None:
    """Record search metrics."""
    SEARCHES_TOTAL.labels(search_type=search_type).inc()
    SEARCH_LATENCY.labels(search_type=search_type).observe(duration)


def update_document_counts(documents: int, chunks: int) -> None:
    """Update document count gauges."""
    DOCUMENTS_TOTAL.set(documents)
    CHUNKS_TOTAL.set(chunks)


def update_pool_metrics(database: str, size: int, used: int) -> None:
    """Update connection pool metrics."""
    DB_CONNECTION_POOL_SIZE.labels(database=database).set(size)
    DB_CONNECTION_POOL_USED.labels(database=database).set(used)


@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Expose Prometheus metrics.",
)
async def metrics() -> Response:
    """Return Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
```

**src/api/middleware/metrics.py:**
```python
"""Metrics middleware."""
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.routers.metrics import record_request


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to record request metrics."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Record request metrics."""
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time

        # Record metrics (skip health/metrics endpoints)
        if not request.url.path.startswith("/api/v1/health") and \
           not request.url.path.startswith("/api/v1/metrics"):
            record_request(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                duration=duration,
            )

        return response
```

**완료 기준:**
- [ ] Prometheus 메트릭 정의
- [ ] /metrics 엔드포인트
- [ ] 메트릭 미들웨어

---

### Step 3: 테스트 작성 (1h)

**작업 내용:**
1. Health check 테스트
2. Metrics 테스트

**tests/unit/test_api/test_health.py:**
```python
"""Tests for health check."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.health import router, set_clients


@pytest.fixture
def healthy_clients() -> dict:
    """Create healthy mock clients."""
    return {
        "postgres": MagicMock(ping=AsyncMock(return_value=True)),
        "milvus": MagicMock(ping=AsyncMock(return_value=True)),
        "neo4j": MagicMock(ping=AsyncMock(return_value=True)),
        "kafka": MagicMock(ping=AsyncMock(return_value=True)),
    }


@pytest.fixture
def unhealthy_clients() -> dict:
    """Create unhealthy mock clients."""
    return {
        "postgres": MagicMock(ping=AsyncMock(return_value=True)),
        "milvus": MagicMock(ping=AsyncMock(return_value=False)),
        "neo4j": MagicMock(ping=AsyncMock(return_value=True)),
        "kafka": MagicMock(ping=AsyncMock(return_value=True)),
    }


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


class TestHealthCheck:
    """Tests for health check endpoint."""

    def test_health_all_up(
        self,
        client: TestClient,
        healthy_clients: dict,
    ) -> None:
        """Test health when all services are up."""
        set_clients(**healthy_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert all(c["status"] == "up" for c in data["checks"].values())

    def test_health_one_down(
        self,
        client: TestClient,
        unhealthy_clients: dict,
    ) -> None:
        """Test health when one service is down."""
        set_clients(**unhealthy_clients)

        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["checks"]["milvus"]["status"] == "down"

    def test_liveness(self, client: TestClient) -> None:
        """Test liveness probe."""
        response = client.get("/api/v1/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    def test_readiness_healthy(
        self,
        client: TestClient,
        healthy_clients: dict,
    ) -> None:
        """Test readiness when healthy."""
        set_clients(**healthy_clients)

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 200

    def test_readiness_unhealthy(
        self,
        client: TestClient,
        unhealthy_clients: dict,
    ) -> None:
        """Test readiness when unhealthy."""
        set_clients(**unhealthy_clients)

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 503


class TestMetrics:
    """Tests for metrics."""

    def test_metrics_endpoint(self) -> None:
        """Test metrics endpoint returns Prometheus format."""
        from src.api.routers.metrics import router as metrics_router

        app = FastAPI()
        app.include_router(metrics_router, prefix="/api/v1")
        test_client = TestClient(app)

        response = test_client.get("/api/v1/metrics")

        assert response.status_code == 200
        assert "knowledge_store" in response.text
```

**완료 기준:**
- [ ] Health check 테스트
- [ ] 부분 장애 테스트
- [ ] Readiness 테스트
- [ ] Metrics 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_health_all_up` | 모두 정상 | healthy |
| `test_health_one_down` | 하나 장애 | unhealthy |
| `test_liveness` | 생존 확인 | 200 |
| `test_readiness` | 준비 확인 | 상태에 따라 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Health check 과부하 | Medium | Low | 캐싱, 타임아웃 |
| Metrics 카디널리티 | Medium | Medium | 레이블 제한 |

---

## 6. Definition of Done

- [ ] `src/api/routers/health.py` 생성
- [ ] `src/api/routers/metrics.py` 생성
- [ ] GET /health 구현
- [ ] GET /metrics 구현
- [ ] Kubernetes probes 지원
- [ ] 테스트 작성 및 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Health Check | 1.5h | - |
| Step 2: Prometheus Metrics | 1.5h | - |
| Step 3: 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
