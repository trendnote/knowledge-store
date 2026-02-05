"""PostgreSQL async client with connection pooling.

This module provides an async PostgreSQL client using asyncpg with
connection pool management, transaction support, and query helpers.

Example:
    >>> from src.infrastructure.database import get_postgres_client
    >>> client = get_postgres_client()
    >>> await client.connect()
    >>> rows = await client.fetch("SELECT * FROM documents LIMIT 10")
    >>> await client.disconnect()
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import asyncpg
from asyncpg import Pool, Record

if TYPE_CHECKING:
    from asyncpg import Connection

from src.config import PostgresSettings


class PostgresClient:
    """Async PostgreSQL client with connection pool management.

    This client provides:
    - Connection pool management (connect/disconnect)
    - Transaction context managers for atomic operations
    - Query helpers (execute, fetch, fetchrow, fetchval)
    - Health check via ping

    Example:
        >>> client = PostgresClient(settings)
        >>> await client.connect()
        >>> async with client.transaction() as conn:
        ...     await conn.execute("INSERT INTO test VALUES ($1)", 1)
        >>> await client.disconnect()
    """

    def __init__(self, settings: PostgresSettings) -> None:
        """Initialize PostgreSQL client.

        Args:
            settings: PostgreSQL connection settings
        """
        self._settings = settings
        self._pool: Pool | None = None

    @property
    def pool(self) -> Pool:
        """Get connection pool.

        Returns:
            Connection pool instance

        Raises:
            RuntimeError: If client is not connected
        """
        if self._pool is None:
            raise RuntimeError("PostgresClient is not connected. Call connect() first.")
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._pool is not None

    async def connect(self) -> None:
        """Create connection pool.

        This method is idempotent - calling it multiple times
        will not create additional pools.
        """
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.dsn,
            min_size=5,
            max_size=self._settings.pool_size,
            max_inactive_connection_lifetime=300.0,
            command_timeout=60.0,
            statement_cache_size=100,
        )

    async def disconnect(self) -> None:
        """Close connection pool.

        This method is idempotent - calling it multiple times
        is safe.
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        """Check if database is reachable.

        Returns:
            True if database is accessible, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Connection]:
        """Acquire a connection from the pool.

        Yields:
            Database connection

        Example:
            >>> async with client.acquire() as conn:
            ...     await conn.execute("SELECT 1")
        """
        async with self.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Connection]:
        """Create a transaction context.

        The transaction is automatically committed on success
        and rolled back on exception.

        Yields:
            Database connection with active transaction

        Example:
            >>> async with client.transaction() as conn:
            ...     await conn.execute("INSERT INTO test VALUES ($1)", 1)
            ...     await conn.execute("INSERT INTO test VALUES ($1)", 2)
            ...     # Auto-commit on success, auto-rollback on exception
        """
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query and return status.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            Command status string (e.g., 'INSERT 0 1')

        Example:
            >>> status = await client.execute(
            ...     "INSERT INTO documents (title) VALUES ($1)",
            ...     "My Document"
            ... )
            >>> print(status)  # 'INSERT 0 1'
        """
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        """Execute a query with multiple parameter sets.

        Args:
            query: SQL query with $1, $2, ... placeholders
            args: List of parameter tuples

        Example:
            >>> await client.executemany(
            ...     "INSERT INTO documents (title) VALUES ($1)",
            ...     [("Doc 1",), ("Doc 2",), ("Doc 3",)]
            ... )
        """
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)

    async def fetch(self, query: str, *args: Any) -> list[Record]:
        """Execute a query and return all rows.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            List of Record objects (dict-like)

        Example:
            >>> rows = await client.fetch("SELECT * FROM documents LIMIT 10")
            >>> for row in rows:
            ...     print(row["title"])
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Record | None:
        """Execute a query and return first row.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            Single Record or None if no results

        Example:
            >>> row = await client.fetchrow(
            ...     "SELECT * FROM documents WHERE id = $1",
            ...     doc_id
            ... )
            >>> if row:
            ...     print(row["title"])
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        """Execute a query and return first column of first row.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters
            column: Column index to return (default: 0)

        Returns:
            Single value or None if no results

        Example:
            >>> count = await client.fetchval("SELECT count(*) FROM documents")
            >>> print(f"Total documents: {count}")
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)

    async def exists(self, query: str, *args: Any) -> bool:
        """Check if any rows exist for a query.

        Args:
            query: SQL query with $1, $2, ... placeholders
            *args: Query parameters

        Returns:
            True if at least one row exists

        Example:
            >>> exists = await client.exists(
            ...     "SELECT 1 FROM documents WHERE id = $1",
            ...     doc_id
            ... )
        """
        result = await self.fetchval(query, *args)
        return result is not None


# Singleton instance
_client: PostgresClient | None = None


def get_postgres_client(settings: PostgresSettings | None = None) -> PostgresClient:
    """Get or create PostgreSQL client singleton.

    Args:
        settings: PostgreSQL settings (required on first call,
                  or auto-loaded from environment)

    Returns:
        PostgresClient instance

    Example:
        >>> client = get_postgres_client()
        >>> await client.connect()
    """
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings

            settings = get_settings().postgres
        _client = PostgresClient(settings)
    return _client


async def close_postgres_client() -> None:
    """Close the PostgreSQL client singleton.

    This should be called during application shutdown.
    """
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None


def reset_postgres_client() -> None:
    """Reset the PostgreSQL client singleton (for testing)."""
    global _client
    _client = None
