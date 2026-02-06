"""PostgreSQL repository module.

This module provides data access layer for PostgreSQL:
- PostgresRepository: Main repository class
"""

from src.repositories.postgres.repository import (
    PostgresRepository,
    get_postgres_repository,
    reset_postgres_repository,
)

__all__ = [
    "PostgresRepository",
    "get_postgres_repository",
    "reset_postgres_repository",
]
