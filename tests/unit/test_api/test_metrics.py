"""Tests for metrics router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    from src.api.routers.metrics import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


# =============================================================================
# Test Metrics Endpoint
# =============================================================================


class TestMetricsEndpoint:
    """Tests for /metrics endpoint."""

    def test_metrics_returns_prometheus_format(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics endpoint returns Prometheus format."""
        response = client.get("/api/v1/metrics")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_contains_request_counter(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics contains request counter."""
        response = client.get("/api/v1/metrics")

        assert "knowledge_store_requests_total" in response.text

    def test_metrics_contains_request_latency(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics contains request latency histogram."""
        response = client.get("/api/v1/metrics")

        assert "knowledge_store_request_duration_seconds" in response.text

    def test_metrics_contains_error_counter(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics contains error counter."""
        response = client.get("/api/v1/metrics")

        assert "knowledge_store_errors_total" in response.text

    def test_metrics_contains_business_metrics(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics contains business metrics."""
        response = client.get("/api/v1/metrics")

        assert "knowledge_store_documents_total" in response.text
        assert "knowledge_store_chunks_total" in response.text
        assert "knowledge_store_searches_total" in response.text

    def test_metrics_contains_db_pool_metrics(
        self,
        client: TestClient,
    ) -> None:
        """Test metrics contains database pool metrics."""
        response = client.get("/api/v1/metrics")

        assert "knowledge_store_db_pool_size" in response.text
        assert "knowledge_store_db_pool_used" in response.text


# =============================================================================
# Test Metric Recording Functions
# =============================================================================


class TestRecordRequest:
    """Tests for record_request function."""

    def test_record_request(self) -> None:
        """Test recording a request."""
        from src.api.routers.metrics import REQUEST_COUNT, record_request

        initial_value = REQUEST_COUNT.labels(
            method="GET",
            endpoint="/test",
            status="200",
        )._value.get()

        record_request(
            method="GET",
            endpoint="/test",
            status=200,
            duration=0.5,
        )

        new_value = REQUEST_COUNT.labels(
            method="GET",
            endpoint="/test",
            status="200",
        )._value.get()

        assert new_value == initial_value + 1

    def test_record_request_latency(self) -> None:
        """Test recording request latency."""
        from src.api.routers.metrics import REQUEST_LATENCY, record_request

        record_request(
            method="POST",
            endpoint="/documents",
            status=201,
            duration=0.25,
        )

        # Verify histogram was updated (check sum)
        sample = REQUEST_LATENCY.labels(
            method="POST",
            endpoint="/documents",
        )._sum.get()

        assert sample > 0


class TestRecordError:
    """Tests for record_error function."""

    def test_record_error(self) -> None:
        """Test recording an error."""
        from src.api.routers.metrics import ERROR_COUNT, record_error

        initial_value = ERROR_COUNT.labels(
            type="database",
            component="postgres",
        )._value.get()

        record_error(error_type="database", component="postgres")

        new_value = ERROR_COUNT.labels(
            type="database",
            component="postgres",
        )._value.get()

        assert new_value == initial_value + 1


class TestRecordSearch:
    """Tests for record_search function."""

    def test_record_search(self) -> None:
        """Test recording a search."""
        from src.api.routers.metrics import SEARCHES_TOTAL, record_search

        initial_value = SEARCHES_TOTAL.labels(search_type="hybrid")._value.get()

        record_search(search_type="hybrid", duration=0.1)

        new_value = SEARCHES_TOTAL.labels(search_type="hybrid")._value.get()

        assert new_value == initial_value + 1

    def test_record_search_latency(self) -> None:
        """Test recording search latency."""
        from src.api.routers.metrics import SEARCH_LATENCY, record_search

        record_search(search_type="vector", duration=0.05)

        sample = SEARCH_LATENCY.labels(search_type="vector")._sum.get()
        assert sample > 0


class TestUpdateDocumentCounts:
    """Tests for update_document_counts function."""

    def test_update_document_counts(self) -> None:
        """Test updating document counts."""
        from src.api.routers.metrics import (
            CHUNKS_TOTAL,
            DOCUMENTS_TOTAL,
            update_document_counts,
        )

        update_document_counts(documents=100, chunks=500)

        assert DOCUMENTS_TOTAL._value.get() == 100
        assert CHUNKS_TOTAL._value.get() == 500

    def test_update_document_counts_overwrites(self) -> None:
        """Test that update overwrites previous values."""
        from src.api.routers.metrics import (
            DOCUMENTS_TOTAL,
            update_document_counts,
        )

        update_document_counts(documents=100, chunks=500)
        update_document_counts(documents=50, chunks=250)

        assert DOCUMENTS_TOTAL._value.get() == 50


class TestUpdatePoolMetrics:
    """Tests for update_pool_metrics function."""

    def test_update_pool_metrics(self) -> None:
        """Test updating pool metrics."""
        from src.api.routers.metrics import (
            DB_CONNECTION_POOL_SIZE,
            DB_CONNECTION_POOL_USED,
            update_pool_metrics,
        )

        update_pool_metrics(database="postgres", size=10, used=3)

        assert DB_CONNECTION_POOL_SIZE.labels(database="postgres")._value.get() == 10
        assert DB_CONNECTION_POOL_USED.labels(database="postgres")._value.get() == 3

    def test_update_pool_metrics_multiple_databases(self) -> None:
        """Test updating pool metrics for multiple databases."""
        from src.api.routers.metrics import (
            DB_CONNECTION_POOL_SIZE,
            update_pool_metrics,
        )

        update_pool_metrics(database="postgres", size=10, used=3)
        update_pool_metrics(database="milvus", size=5, used=2)

        assert DB_CONNECTION_POOL_SIZE.labels(database="postgres")._value.get() == 10
        assert DB_CONNECTION_POOL_SIZE.labels(database="milvus")._value.get() == 5
