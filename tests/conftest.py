"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Load .env file before importing src modules that require settings
# This ensures environment variables are available during import
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)
else:
    # Set minimal test defaults if .env doesn't exist
    os.environ.setdefault("POSTGRES_USER", "test_user")
    os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5433")
    os.environ.setdefault("POSTGRES_DB", "test_db")
    os.environ.setdefault("MILVUS_HOST", "localhost")
    os.environ.setdefault("MILVUS_PORT", "19531")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "test_password")
    os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9093")


@pytest.fixture
def anyio_backend() -> str:
    """Configure anyio to use asyncio backend."""
    return "asyncio"


@pytest.fixture
def client():
    """Create a test client for the FastAPI application.

    This fixture lazily imports the app to avoid import-time settings
    validation issues.
    """
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    # Mock the lifespan dependencies to avoid real DB connections
    with (
        patch("src.api.dependencies.init_clients", new_callable=AsyncMock),
        patch("src.api.dependencies.init_services", new_callable=AsyncMock),
        patch("src.api.dependencies.close_clients", new_callable=AsyncMock),
        patch("src.api.routers.health.set_clients"),
        patch(
            "src.api.dependencies.get_clients_for_health",
            return_value={
                "postgres": None,
                "milvus": None,
                "neo4j": None,
                "kafka": None,
            },
        ),
    ):
        from src.main import create_app

        app = create_app()
        with TestClient(app) as test_client:
            yield test_client
