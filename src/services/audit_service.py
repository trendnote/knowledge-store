"""Audit service for logging user actions.

This module provides the AuditService class for asynchronous, batched
audit logging with minimal performance impact on the main application flow.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Protocol

from src.domain.audit import (
    AuditAction,
    AuditLogEntry,
    AuditQuery,
    ResourceType,
)

logger = logging.getLogger(__name__)


class AuditRepositoryProtocol(Protocol):
    """Protocol for audit repository.

    Defines the interface that audit repositories must implement.
    """

    async def create_audit_log(self, log: AuditLogEntry) -> AuditLogEntry:
        """Create a single audit log entry.

        Args:
            log: Audit log entry to create

        Returns:
            Created audit log entry with ID
        """
        ...

    async def create_audit_logs_batch(self, logs: list[AuditLogEntry]) -> int:
        """Create multiple audit log entries in batch.

        Args:
            logs: List of audit log entries

        Returns:
            Number of entries created
        """
        ...

    async def query_audit_logs(self, query: AuditQuery) -> list[AuditLogEntry]:
        """Query audit logs with filters.

        Args:
            query: Query parameters

        Returns:
            List of matching audit log entries
        """
        ...


class AuditService:
    """Service for audit logging.

    Provides asynchronous, batched audit logging to minimize
    performance impact on the main application flow.

    Attributes:
        _repository: Audit repository for persistence
        _batch_size: Number of logs to batch before flush
        _flush_interval: Maximum time between flushes in seconds
        _buffer: Internal buffer for pending logs
        _max_buffer_size: Maximum buffer size to prevent memory issues
    """

    DEFAULT_BATCH_SIZE = 100
    DEFAULT_FLUSH_INTERVAL = 5.0
    DEFAULT_MAX_BUFFER_SIZE = 10000

    def __init__(
        self,
        repository: AuditRepositoryProtocol,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL,
        max_buffer_size: int = DEFAULT_MAX_BUFFER_SIZE,
    ) -> None:
        """Initialize audit service.

        Args:
            repository: Audit repository for persistence
            batch_size: Number of logs to batch before flush
            flush_interval_seconds: Maximum time between flushes
            max_buffer_size: Maximum buffer size to prevent memory issues
        """
        self._repository = repository
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds
        self._max_buffer_size = max_buffer_size
        self._buffer: deque[AuditLogEntry] = deque(maxlen=max_buffer_size)
        self._flush_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._started = False

    @property
    def buffer_size(self) -> int:
        """Get current buffer size.

        Returns:
            Number of pending logs in buffer
        """
        return len(self._buffer)

    @property
    def is_started(self) -> bool:
        """Check if service is started.

        Returns:
            True if background flush task is running
        """
        return self._started

    async def start(self) -> None:
        """Start background flush task.

        Begins periodic flushing of the audit log buffer.
        Safe to call multiple times.
        """
        if self._started:
            return

        self._flush_task = asyncio.create_task(self._periodic_flush())
        self._started = True
        logger.info("Audit service started")

    async def stop(self) -> None:
        """Stop and flush remaining logs.

        Cancels the background flush task and performs a final
        flush of any remaining logs in the buffer.
        """
        if not self._started:
            return

        self._started = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush remaining logs
        await self._flush()
        logger.info("Audit service stopped")

    async def _periodic_flush(self) -> None:
        """Periodically flush buffer.

        Runs as a background task, flushing the buffer at regular intervals.
        """
        while self._started:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")

    async def _flush(self) -> None:
        """Flush buffer to database.

        Takes all logs from buffer and persists them in batch.
        On failure, logs are returned to the buffer for retry.
        """
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
            # Put back in buffer for retry (up to max size)
            async with self._lock:
                for log in reversed(logs):
                    if len(self._buffer) < self._max_buffer_size:
                        self._buffer.appendleft(log)
                    else:
                        logger.warning("Audit log buffer full, dropping oldest logs")
                        break

    async def _add_log(self, log: AuditLogEntry) -> None:
        """Add log to buffer.

        Args:
            log: Audit log entry to add
        """
        async with self._lock:
            self._buffer.append(log)

            if len(self._buffer) >= self._batch_size:
                # Trigger flush in background
                asyncio.create_task(self._flush())

    async def log_search(
        self,
        user_id: str,
        query: str,
        retrieved_docs: list[str],
        search_type: str = "hybrid",
        duration_ms: float | None = None,
        result_count: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log search request.

        Args:
            user_id: User who performed search
            query: Search query text
            retrieved_docs: List of retrieved document UUIDs
            search_type: Type of search (dense, sparse, graph, hybrid)
            duration_ms: Search duration in milliseconds
            result_count: Number of results returned
            ip_address: Client IP address
            user_agent: Client user agent
        """
        action_map = {
            "dense": AuditAction.SEARCH_DENSE,
            "sparse": AuditAction.SEARCH_SPARSE,
            "graph": AuditAction.SEARCH_GRAPH,
            "hybrid": AuditAction.SEARCH_HYBRID,
        }

        metadata: dict[str, Any] = {}
        if duration_ms is not None:
            metadata["duration_ms"] = duration_ms
        if result_count is not None:
            metadata["result_count"] = result_count

        log = AuditLogEntry(
            user_id=user_id,
            action=action_map.get(search_type, AuditAction.SEARCH),
            resource_type=ResourceType.SEARCH,
            query_text=query,
            retrieved_docs=retrieved_docs,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await self._add_log(log)

    async def log_document_access(
        self,
        user_id: str,
        doc_uuid: str,
        action: AuditAction,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log document access.

        Args:
            user_id: User who accessed document
            doc_uuid: Document UUID
            action: Action performed (create, read, update, delete, list)
            ip_address: Client IP address
            user_agent: Client user agent
            metadata: Additional context
        """
        log = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=ResourceType.DOCUMENT,
            resource_id=doc_uuid,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
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
        user_agent: str | None = None,
    ) -> None:
        """Log permission change.

        Args:
            user_id: User who changed permission
            doc_uuid: Document UUID
            action: Action (grant or revoke)
            principal_type: Type of principal (user, group, org, role)
            principal_id: Principal ID
            permission: Permission level (read, write, admin, delete)
            ip_address: Client IP address
            user_agent: Client user agent
        """
        log = AuditLogEntry(
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
            user_agent=user_agent,
        )

        await self._add_log(log)

    async def log_export(
        self,
        user_id: str,
        doc_uuid: str,
        export_format: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Log document export.

        Args:
            user_id: User who exported document
            doc_uuid: Document UUID
            export_format: Export format (pdf, docx, etc.)
            ip_address: Client IP address
            user_agent: Client user agent
        """
        log = AuditLogEntry(
            user_id=user_id,
            action=AuditAction.EXPORT,
            resource_type=ResourceType.DOCUMENT,
            resource_id=doc_uuid,
            metadata={"export_format": export_format},
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await self._add_log(log)

    async def query_logs(self, query: AuditQuery) -> list[AuditLogEntry]:
        """Query audit logs.

        Args:
            query: Query parameters for filtering

        Returns:
            List of matching audit log entries
        """
        return await self._repository.query_audit_logs(query)

    async def flush(self) -> None:
        """Manually flush the buffer.

        Forces immediate persistence of all buffered logs.
        """
        await self._flush()


# =============================================================================
# Global Instance Management
# =============================================================================

_audit_service: AuditService | None = None


def get_audit_service() -> AuditService | None:
    """Get the global audit service instance.

    Returns:
        AuditService instance or None if not configured
    """
    return _audit_service


def set_audit_service(service: AuditService | None) -> None:
    """Set the global audit service instance.

    Args:
        service: AuditService instance or None to clear
    """
    global _audit_service
    _audit_service = service


async def audit_search(
    user_id: str,
    query: str,
    retrieved_docs: list[str],
    search_type: str = "hybrid",
    duration_ms: float | None = None,
    result_count: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Log search if audit service is available.

    Convenience function for logging searches without explicit
    service reference.

    Args:
        user_id: User who performed search
        query: Search query text
        retrieved_docs: List of retrieved document UUIDs
        search_type: Type of search
        duration_ms: Search duration in milliseconds
        result_count: Number of results returned
        ip_address: Client IP address
        user_agent: Client user agent
    """
    if _audit_service:
        await _audit_service.log_search(
            user_id=user_id,
            query=query,
            retrieved_docs=retrieved_docs,
            search_type=search_type,
            duration_ms=duration_ms,
            result_count=result_count,
            ip_address=ip_address,
            user_agent=user_agent,
        )


async def audit_document(
    user_id: str,
    doc_uuid: str,
    action: AuditAction,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log document access if audit service is available.

    Convenience function for logging document access without explicit
    service reference.

    Args:
        user_id: User who accessed document
        doc_uuid: Document UUID
        action: Action performed
        ip_address: Client IP address
        user_agent: Client user agent
        metadata: Additional context
    """
    if _audit_service:
        await _audit_service.log_document_access(
            user_id=user_id,
            doc_uuid=doc_uuid,
            action=action,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata,
        )


async def audit_permission(
    user_id: str,
    doc_uuid: str,
    action: AuditAction,
    principal_type: str,
    principal_id: str,
    permission: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Log permission change if audit service is available.

    Convenience function for logging permission changes without explicit
    service reference.

    Args:
        user_id: User who changed permission
        doc_uuid: Document UUID
        action: Action (grant or revoke)
        principal_type: Type of principal
        principal_id: Principal ID
        permission: Permission level
        ip_address: Client IP address
        user_agent: Client user agent
    """
    if _audit_service:
        await _audit_service.log_permission_change(
            user_id=user_id,
            doc_uuid=doc_uuid,
            action=action,
            principal_type=principal_type,
            principal_id=principal_id,
            permission=permission,
            ip_address=ip_address,
            user_agent=user_agent,
        )
