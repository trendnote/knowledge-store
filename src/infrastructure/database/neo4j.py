"""Neo4j async graph database client.

This module provides an async client for Neo4j graph database with support for:
- Async driver management with connection pooling
- Session context manager
- Read/Write transaction execution
- Query helper methods

Example:
    >>> from src.infrastructure.database import get_neo4j_client
    >>> client = get_neo4j_client()
    >>> await client.connect()
    >>> records = await client.execute_query("MATCH (n) RETURN n LIMIT 10")
    >>> await client.close()
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import ServiceUnavailable

from src.config import Neo4jSettings

if TYPE_CHECKING:
    from neo4j import AsyncDriver, AsyncSession


class Neo4jClient:
    """Async Neo4j client for graph operations.

    This client provides:
    - Connection management (connect/close)
    - Session context manager
    - Read/Write transaction execution
    - Query helper methods

    Note:
        Uses neo4j official async driver with built-in connection pooling.
    """

    def __init__(self, settings: Neo4jSettings) -> None:
        """Initialize Neo4j client.

        Args:
            settings: Neo4j connection settings
        """
        self._settings = settings
        self._driver: AsyncDriver | None = None

    @property
    def driver(self) -> AsyncDriver:
        """Get driver.

        Returns:
            AsyncDriver instance

        Raises:
            RuntimeError: If client is not connected
        """
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call connect() first.")
        return self._driver

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._driver is not None

    async def connect(self) -> None:
        """Create driver and verify connectivity.

        This method is idempotent - calling it multiple times
        will not create additional drivers.
        """
        if self._driver is not None:
            return

        self._driver = AsyncGraphDatabase.driver(
            self._settings.uri,
            auth=(self._settings.user, self._settings.password.get_secret_value()),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
        )

        # Verify connectivity
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        """Close driver.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def ping(self) -> bool:
        """Check if Neo4j is reachable.

        Returns:
            True if Neo4j is accessible, False otherwise
        """
        try:
            if self._driver is None:
                return False
            await self._driver.verify_connectivity()
            return True
        except (ServiceUnavailable, RuntimeError, Exception):
            return False

    @asynccontextmanager
    async def session(self, database: str | None = None) -> AsyncIterator[AsyncSession]:
        """Create a session context.

        Args:
            database: Database name (default: neo4j)

        Yields:
            AsyncSession instance

        Example:
            >>> async with client.session() as session:
            ...     result = await session.run("MATCH (n) RETURN n")
        """
        async with self.driver.session(database=database or "neo4j") as session:
            yield session

    # =========================================================================
    # Transaction Methods
    # =========================================================================

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read query within a transaction.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries

        Example:
            >>> records = await client.execute_read(
            ...     "MATCH (n:Document) WHERE n.status = $status RETURN n",
            ...     {"status": "published"}
            ... )
        """

        async def _read_tx(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records

        async with self.session(database) as session:
            return await session.execute_read(_read_tx)

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a write query within a transaction.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries

        Example:
            >>> records = await client.execute_write(
            ...     "CREATE (n:Document {title: $title}) RETURN n",
            ...     {"title": "My Document"}
            ... )
        """

        async def _write_tx(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records

        async with self.session(database) as session:
            return await session.execute_write(_write_tx)

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a query (auto-commit mode).

        For simple queries without explicit transaction control.
        Use execute_read/execute_write for transactional guarantees.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries

        Example:
            >>> records = await client.execute_query("MATCH (n) RETURN n LIMIT 10")
        """
        async with self.session(database) as session:
            result = await session.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def execute_query_single(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> dict[str, Any] | None:
        """Execute query and return single record.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            Single record dict or None
        """
        records = await self.execute_query(query, parameters, database)
        return records[0] if records else None

    async def execute_query_value(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
        key: str = "value",
    ) -> Any:
        """Execute query and return single value.

        Args:
            query: Cypher query returning {key: value}
            parameters: Query parameters
            database: Database name
            key: Key to extract from result

        Returns:
            Single value or None
        """
        record = await self.execute_query_single(query, parameters, database)
        return record.get(key) if record else None

    async def count_nodes(self, label: str, database: str | None = None) -> int:
        """Count nodes with given label.

        Args:
            label: Node label
            database: Database name

        Returns:
            Node count
        """
        result = await self.execute_query_value(
            f"MATCH (n:{label}) RETURN count(n) as value",
            database=database,
        )
        return result or 0

    async def node_exists(
        self,
        label: str,
        property_name: str,
        property_value: Any,
        database: str | None = None,
    ) -> bool:
        """Check if node exists.

        Args:
            label: Node label
            property_name: Property to check
            property_value: Property value
            database: Database name

        Returns:
            True if node exists
        """
        result = await self.execute_query_value(
            f"MATCH (n:{label} {{{property_name}: $value}}) RETURN count(n) > 0 as value",
            {"value": property_value},
            database=database,
        )
        return result or False


# =============================================================================
# Singleton Factory
# =============================================================================

_client: Neo4jClient | None = None


def get_neo4j_client(settings: Neo4jSettings | None = None) -> Neo4jClient:
    """Get or create Neo4j client singleton.

    Args:
        settings: Neo4j settings (required on first call,
                  or auto-loaded from environment)

    Returns:
        Neo4jClient instance
    """
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings

            settings = get_settings().neo4j
        _client = Neo4jClient(settings)
    return _client


async def close_neo4j_client() -> None:
    """Close the Neo4j client singleton."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def reset_neo4j_client() -> None:
    """Reset the Neo4j client singleton (for testing)."""
    global _client
    _client = None
