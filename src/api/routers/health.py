"""Health check router.

This module provides health check endpoints for the Knowledge Store API:
- /health: Full health check with all components
- /health/live: Kubernetes liveness probe
- /health/ready: Kubernetes readiness probe
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class CheckResult(BaseModel):
    """Single health check result.

    Attributes:
        status: Component status ("up" or "down")
        latency_ms: Response latency in milliseconds
        error: Error message if status is down
    """

    status: str  # "up" or "down"
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response.

    Attributes:
        status: Overall system status ("healthy" or "unhealthy")
        timestamp: Time of the health check
        checks: Individual component check results
    """

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
    """Set client references for health checks.

    Args:
        postgres: PostgreSQL client with ping method
        milvus: Milvus client with ping method
        neo4j: Neo4j client with ping method
        kafka: Kafka producer with ping method
    """
    global _postgres_client, _milvus_client, _neo4j_client, _kafka_producer
    _postgres_client = postgres
    _milvus_client = milvus
    _neo4j_client = neo4j
    _kafka_producer = kafka


def get_clients() -> dict[str, Any]:
    """Get current client references.

    Returns:
        Dictionary of client references
    """
    return {
        "postgres": _postgres_client,
        "milvus": _milvus_client,
        "neo4j": _neo4j_client,
        "kafka": _kafka_producer,
    }


def reset_clients() -> None:
    """Reset all client references to None. Used for testing."""
    global _postgres_client, _milvus_client, _neo4j_client, _kafka_producer
    _postgres_client = None
    _milvus_client = None
    _neo4j_client = None
    _kafka_producer = None


async def _check_postgres() -> CheckResult:
    """Check PostgreSQL connection.

    Returns:
        CheckResult with status and latency
    """
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
        logger.warning(f"PostgreSQL health check failed: {e}")
        return CheckResult(status="down", error=str(e))


async def _check_milvus() -> CheckResult:
    """Check Milvus connection.

    Returns:
        CheckResult with status and latency
    """
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
        logger.warning(f"Milvus health check failed: {e}")
        return CheckResult(status="down", error=str(e))


async def _check_neo4j() -> CheckResult:
    """Check Neo4j connection.

    Returns:
        CheckResult with status and latency
    """
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
        logger.warning(f"Neo4j health check failed: {e}")
        return CheckResult(status="down", error=str(e))


async def _check_kafka() -> CheckResult:
    """Check Kafka connection.

    Returns:
        CheckResult with status and latency
    """
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
        logger.warning(f"Kafka health check failed: {e}")
        return CheckResult(status="down", error=str(e))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check health of all system components.",
)
async def health_check() -> HealthResponse:
    """Check system health.

    Performs parallel health checks on all configured components
    (PostgreSQL, Milvus, Neo4j, Kafka) and returns aggregated results.

    Returns:
        HealthResponse with overall status and individual check results
    """
    # Run all checks in parallel
    results = await asyncio.gather(
        _check_postgres(),
        _check_milvus(),
        _check_neo4j(),
        _check_kafka(),
        return_exceptions=True,
    )

    checks = {
        "postgres": (
            results[0]
            if not isinstance(results[0], Exception)
            else CheckResult(status="down", error=str(results[0]))
        ),
        "milvus": (
            results[1]
            if not isinstance(results[1], Exception)
            else CheckResult(status="down", error=str(results[1]))
        ),
        "neo4j": (
            results[2]
            if not isinstance(results[2], Exception)
            else CheckResult(status="down", error=str(results[2]))
        ),
        "kafka": (
            results[3]
            if not isinstance(results[3], Exception)
            else CheckResult(status="down", error=str(results[3]))
        ),
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
    """Kubernetes liveness probe.

    Simple check that returns 200 if the service is alive.
    Does not check component connectivity.

    Returns:
        Dictionary with status "alive"
    """
    return {"status": "alive"}


@router.get(
    "/health/ready",
    summary="Readiness Probe",
    description="Readiness check for Kubernetes.",
)
async def readiness() -> dict:
    """Kubernetes readiness probe.

    Checks if the service is ready to accept traffic by verifying
    all components are healthy. Returns 503 if not ready.

    Returns:
        Dictionary with status "ready"

    Raises:
        HTTPException: 503 if service is not ready
    """
    health = await health_check()

    if health.status != "healthy":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready",
        )

    return {"status": "ready"}
