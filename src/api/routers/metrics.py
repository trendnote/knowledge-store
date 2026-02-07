"""Prometheus metrics router.

This module provides Prometheus metrics for the Knowledge Store API:
- Request metrics (count, latency)
- Error metrics
- Business metrics (documents, chunks, searches)
- Database connection pool metrics
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
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
    """Record request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Request endpoint path
        status: HTTP status code
        duration: Request duration in seconds
    """
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


def record_error(error_type: str, component: str) -> None:
    """Record error metrics.

    Args:
        error_type: Type of error (database, validation, etc.)
        component: Component where error occurred
    """
    ERROR_COUNT.labels(type=error_type, component=component).inc()


def record_search(search_type: str, duration: float) -> None:
    """Record search metrics.

    Args:
        search_type: Type of search (vector, keyword, hybrid)
        duration: Search duration in seconds
    """
    SEARCHES_TOTAL.labels(search_type=search_type).inc()
    SEARCH_LATENCY.labels(search_type=search_type).observe(duration)


def update_document_counts(documents: int, chunks: int) -> None:
    """Update document count gauges.

    Args:
        documents: Total number of documents
        chunks: Total number of chunks
    """
    DOCUMENTS_TOTAL.set(documents)
    CHUNKS_TOTAL.set(chunks)


def update_pool_metrics(database: str, size: int, used: int) -> None:
    """Update connection pool metrics.

    Args:
        database: Database name (postgres, milvus, neo4j)
        size: Total pool size
        used: Connections currently in use
    """
    DB_CONNECTION_POOL_SIZE.labels(database=database).set(size)
    DB_CONNECTION_POOL_USED.labels(database=database).set(used)


@router.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Expose Prometheus metrics.",
)
async def metrics() -> Response:
    """Return Prometheus metrics.

    Returns metrics in Prometheus text format for scraping.

    Returns:
        Response with Prometheus-formatted metrics
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
