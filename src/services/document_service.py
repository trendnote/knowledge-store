"""Document service for document CRUD operations.

This module provides business logic for document management:
- Document creation with chunking and embedding
- Document retrieval with ACL enforcement
- Document update with re-embedding
- Document deletion across all stores

The service orchestrates:
1. Text chunking for vector/graph storage
2. Saga-based distributed transactions
3. Kafka event publishing
4. ACL-based access control

Example:
    >>> from src.services.document_service import get_document_service
    >>> service = get_document_service(postgres_repo, saga_coordinator, embedding_service)
    >>> response = await service.create_document(request)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, Protocol
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from src.services.acl_service import AclService, Permission, PrincipalType
    from src.services.saga.coordinator import SagaCoordinator

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================


@dataclass
class DocumentCreateRequest:
    """Request to create a document.

    Attributes:
        title: Document title
        content: Raw content to be chunked
        owner_id: Document owner user ID
        owner_org: Document owner organization
        source: Source system
        source_url: Original document URL
        security_level: Security classification
        metadata: Additional metadata
        chunk_size: Characters per chunk
        chunk_overlap: Overlap between chunks
    """

    title: str
    content: str
    owner_id: str
    owner_org: str = "default"
    source: Literal["wiki", "agit", "gdocs", "slack", "confluence", "notion", "file"] = "file"
    source_url: str | None = None
    security_level: Literal["public", "internal", "confidential"] = "internal"
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_size: int = 500
    chunk_overlap: int = 50


@dataclass
class DocumentUpdateRequest:
    """Request to update a document.

    Attributes:
        title: New document title (None = no change)
        content: New content (None = no change, triggers re-chunking if set)
        status: New status (None = no change)
        security_level: New security level (None = no change)
        metadata: Metadata to merge (None = no change)
    """

    title: str | None = None
    content: str | None = None
    status: Literal["draft", "published", "archived"] | None = None
    security_level: Literal["public", "internal", "confidential"] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class DocumentResponse:
    """Document response model.

    Attributes:
        doc_uuid: Document UUID
        title: Document title
        owner_id: Document owner user ID
        owner_org: Document owner organization
        source: Source system
        source_url: Original document URL
        status: Document status
        security_level: Security classification
        chunk_count: Number of chunks
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: Additional metadata
    """

    doc_uuid: str
    title: str
    owner_id: str
    owner_org: str
    source: str
    status: str
    security_level: str
    chunk_count: int
    created_at: datetime | None
    updated_at: datetime | None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkData:
    """Chunk data for internal processing.

    Attributes:
        chunk_uuid: Chunk UUID
        doc_uuid: Parent document UUID
        version_id: Parent version UUID
        chunk_no: Chunk index/number
        chunk_text: Chunk text content
        char_start: Start character position in original content
        char_end: End character position in original content
    """

    chunk_uuid: str
    doc_uuid: str
    version_id: str
    chunk_no: int
    chunk_text: str
    char_start: int = 0
    char_end: int = 0


# =============================================================================
# Protocols
# =============================================================================


class KafkaProducerProtocol(Protocol):
    """Protocol for Kafka producer."""

    async def send(self, topic: str, message: dict[str, Any]) -> None:
        """Send message to topic."""
        ...


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding service."""

    def encode(self, texts: list[str]) -> Any:
        """Encode texts to embeddings."""
        ...


# =============================================================================
# Document Service
# =============================================================================


class DocumentService:
    """Service for document CRUD operations.

    Orchestrates document lifecycle with:
    - Text chunking (sentence-aware)
    - Saga-based distributed transactions
    - Kafka event publishing
    - ACL-based access control

    Attributes:
        _postgres_repo: PostgreSQL repository
        _saga: Saga coordinator for distributed transactions
        _embedding: Embedding service for vector generation
        _kafka: Kafka producer for events (optional)
        _acl: ACL service for permissions (optional)
    """

    def __init__(
        self,
        postgres_repo: Any,
        saga_coordinator: Any,
        embedding_service: Any,
        kafka_producer: KafkaProducerProtocol | None = None,
        acl_service: Any | None = None,
    ) -> None:
        """Initialize document service.

        Args:
            postgres_repo: PostgreSQL repository
            saga_coordinator: Saga coordinator for distributed transactions
            embedding_service: Embedding service for vector generation
            kafka_producer: Kafka producer for events (optional)
            acl_service: ACL service for permissions (optional)
        """
        self._postgres_repo = postgres_repo
        self._saga = saga_coordinator
        self._embedding = embedding_service
        self._kafka = kafka_producer
        self._acl = acl_service

    # =========================================================================
    # Text Chunking
    # =========================================================================

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[tuple[str, int, int]]:
        """Split text into chunks with position tracking.

        Simple character-based chunking with:
        - Sentence boundary awareness
        - Overlap for context continuity
        - Position tracking for source mapping

        Args:
            text: Text to chunk
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of tuples: (chunk_text, char_start, char_end)
        """
        if not text or not text.strip():
            return []

        # Normalize whitespace but preserve paragraph structure
        lines = text.split("\n")
        normalized_lines = [" ".join(line.split()) for line in lines]
        text = "\n".join(normalized_lines)

        chunks: list[tuple[str, int, int]] = []
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Try to break at sentence/paragraph boundary
            if end < len(text):
                # Look for sentence boundaries
                for sep in ["\n\n", "\n", ". ", "! ", "? ", "; "]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + chunk_overlap:
                        end = last_sep + len(sep)
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append((chunk, start, end))

            # Move start with overlap
            next_start = end - chunk_overlap
            if next_start <= start:
                next_start = end
            start = next_start

        return chunks

    def _create_chunks(
        self,
        doc_uuid: str,
        version_id: str,
        content: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[ChunkData]:
        """Create chunk objects from content.

        Args:
            doc_uuid: Document UUID
            version_id: Version UUID
            content: Text to chunk
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of ChunkData objects
        """
        chunk_tuples = self._chunk_text(content, chunk_size, chunk_overlap)
        return [
            ChunkData(
                chunk_uuid=str(uuid4()),
                doc_uuid=doc_uuid,
                version_id=version_id,
                chunk_no=i,
                chunk_text=text,
                char_start=char_start,
                char_end=char_end,
            )
            for i, (text, char_start, char_end) in enumerate(chunk_tuples)
        ]

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content.

        Args:
            content: Content to hash

        Returns:
            Hex digest of SHA-256 hash
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    # =========================================================================
    # Create Document
    # =========================================================================

    async def create_document(
        self,
        request: DocumentCreateRequest,
    ) -> DocumentResponse:
        """Create a new document.

        Workflow:
        1. Validate content
        2. Create document and version records
        3. Create chunks from content
        4. Execute saga (PostgreSQL → Milvus → Neo4j)
        5. Grant owner access via ACL
        6. Publish Kafka event

        Args:
            request: Document creation request

        Returns:
            Created document response

        Raises:
            ValueError: If content is empty or no chunks created
            RuntimeError: If saga fails
        """
        logger.info(f"Creating document: {request.title}")

        # Validate content
        content = request.content.strip()
        if not content:
            raise ValueError("Document content cannot be empty")

        # Generate UUIDs
        doc_uuid = str(uuid4())
        version_id = str(uuid4())

        # Create chunks
        chunks = self._create_chunks(
            doc_uuid=doc_uuid,
            version_id=version_id,
            content=content,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        if not chunks:
            raise ValueError("No chunks created from content")

        # Build document data for saga
        content_hash = self._compute_content_hash(content)
        now = datetime.utcnow()

        document_data = {
            "doc_uuid": doc_uuid,
            "title": request.title,
            "source": request.source,
            "source_url": request.source_url or "",
            "owner_id": request.owner_id,
            "owner_org": request.owner_org,
            "status": "draft",
            "security_level": request.security_level,
            "created_at": now,
            "updated_at": now,
            "metadata": request.metadata,
        }

        version_data = {
            "version_id": version_id,
            "doc_uuid": doc_uuid,
            "version_no": 1,
            "content_hash": content_hash,
            "content_size": len(content.encode("utf-8")),
            "effective_from": now,
            "created_at": now,
        }

        # Convert chunks to format expected by saga
        chunk_dicts = [
            {
                "chunk_uuid": c.chunk_uuid,
                "doc_uuid": c.doc_uuid,
                "version_id": c.version_id,
                "chunk_no": c.chunk_no,
                "chunk_text": c.chunk_text,
                "char_start": c.char_start,
                "char_end": c.char_end,
            }
            for c in chunks
        ]

        # Create document object for saga
        class DocumentForSaga:
            """Simple object to pass to saga."""

            def __init__(self, data: dict[str, Any], version: dict[str, Any]) -> None:
                self.doc_uuid = data["doc_uuid"]
                self.title = data["title"]
                self.source = data["source"]
                self.source_url = data["source_url"]
                self.owner_id = data["owner_id"]
                self.owner_org = data["owner_org"]
                self.status = data["status"]
                self.security_level = data["security_level"]
                self.created_at = data["created_at"]
                self.updated_at = data["updated_at"]
                self.version = version

        class ChunkForSaga:
            """Simple object to pass to saga."""

            def __init__(self, data: dict[str, Any]) -> None:
                self.chunk_uuid = data["chunk_uuid"]
                self.doc_uuid = data["doc_uuid"]
                self.version_id = data["version_id"]
                self.chunk_no = data["chunk_no"]
                self.chunk_text = data["chunk_text"]
                self.char_start = data.get("char_start", 0)
                self.char_end = data.get("char_end", 0)

        doc_obj = DocumentForSaga(document_data, version_data)
        chunk_objs = [ChunkForSaga(c) for c in chunk_dicts]

        # Execute saga
        logger.info(f"Executing create saga for document: {doc_uuid}")
        result = await self._saga.execute_create_saga(doc_obj, chunk_objs)

        if not result.success:
            logger.error(f"Create saga failed: {result.error}")
            raise RuntimeError(f"Failed to create document: {result.error}")

        # Grant owner access
        if self._acl:
            try:
                from src.services.acl_service import Permission, PrincipalType

                await self._acl.grant_access(
                    doc_uuid=doc_uuid,
                    principal_type=PrincipalType.USER,
                    principal_id=request.owner_id,
                    permission=Permission.ADMIN,
                    granted_by=request.owner_id,
                )
                logger.info(f"Granted owner access: {request.owner_id} -> {doc_uuid}")
            except Exception as e:
                logger.warning(f"Failed to grant ACL access: {e}")

        # Publish Kafka event
        if self._kafka:
            try:
                await self._kafka.send(
                    "document.created",
                    {
                        "doc_uuid": doc_uuid,
                        "title": request.title,
                        "owner_id": request.owner_id,
                        "owner_org": request.owner_org,
                        "chunk_count": len(chunks),
                        "created_at": now.isoformat(),
                    },
                )
                logger.info(f"Published document.created event: {doc_uuid}")
            except Exception as e:
                logger.warning(f"Failed to publish Kafka event: {e}")

        logger.info(f"Document created successfully: {doc_uuid}")

        return DocumentResponse(
            doc_uuid=doc_uuid,
            title=request.title,
            owner_id=request.owner_id,
            owner_org=request.owner_org,
            source=request.source,
            source_url=request.source_url,
            status="draft",
            security_level=request.security_level,
            chunk_count=len(chunks),
            created_at=now,
            updated_at=now,
            metadata=request.metadata,
        )

    # =========================================================================
    # Get Document
    # =========================================================================

    async def get_document(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> DocumentResponse | None:
        """Get a document by UUID.

        Checks ACL permissions before returning document data.

        Args:
            doc_uuid: Document UUID
            user_id: Requesting user ID
            user_groups: User's group memberships

        Returns:
            Document response or None if not found

        Raises:
            PermissionError: If user doesn't have read access
        """
        logger.debug(f"Getting document: {doc_uuid} for user: {user_id}")

        # Check access
        if self._acl:
            from src.services.acl_service import Permission

            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.READ,
            )
            if not has_access:
                raise PermissionError(
                    f"User {user_id} does not have read access to document {doc_uuid}"
                )

        # Get from PostgreSQL
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            return None

        # Get chunk count
        chunks = await self._postgres_repo.get_chunks_by_doc(doc_uuid)
        chunk_count = len(chunks) if chunks else 0

        return DocumentResponse(
            doc_uuid=str(doc.doc_uuid),
            title=doc.title,
            owner_id=doc.owner_id,
            owner_org=doc.owner_org,
            source=doc.source,
            source_url=doc.source_url,
            status=doc.status,
            security_level=doc.security_level,
            chunk_count=chunk_count,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            metadata={},
        )

    # =========================================================================
    # List Documents
    # =========================================================================

    async def list_documents(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DocumentResponse]:
        """List accessible documents.

        Returns only documents the user has access to.

        Args:
            user_id: User ID
            user_groups: User's groups
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of document responses
        """
        logger.debug(f"Listing documents for user: {user_id}")

        # Get accessible doc UUIDs from ACL
        accessible_uuids: list[str] | None = None
        if self._acl:
            accessible_uuids = await self._acl.get_accessible_documents(
                user_id, user_groups
            )
            if not accessible_uuids:
                return []

        # Query PostgreSQL with filters
        docs = await self._postgres_repo.list_documents(
            limit=limit,
            offset=offset,
            status=status,
            owner_id=None,  # Don't filter by owner, ACL handles access
        )

        # Filter by accessible UUIDs if ACL is enabled
        if accessible_uuids is not None:
            accessible_set = set(accessible_uuids)
            docs = [d for d in docs if str(d.doc_uuid) in accessible_set]

        # Build responses
        responses = []
        for doc in docs:
            chunks = await self._postgres_repo.get_chunks_by_doc(doc.doc_uuid)
            responses.append(
                DocumentResponse(
                    doc_uuid=str(doc.doc_uuid),
                    title=doc.title,
                    owner_id=doc.owner_id,
                    owner_org=doc.owner_org,
                    source=doc.source,
                    source_url=doc.source_url,
                    status=doc.status,
                    security_level=doc.security_level,
                    chunk_count=len(chunks) if chunks else 0,
                    created_at=doc.created_at,
                    updated_at=doc.updated_at,
                    metadata={},
                )
            )

        return responses

    # =========================================================================
    # Update Document
    # =========================================================================

    async def update_document(
        self,
        doc_uuid: str,
        request: DocumentUpdateRequest,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> DocumentResponse:
        """Update a document.

        If content changes:
        1. Regenerates chunks and embeddings
        2. Executes update saga (delete old vectors/graph, create new)

        Args:
            doc_uuid: Document UUID
            request: Update request
            user_id: User performing update
            user_groups: User's groups

        Returns:
            Updated document response

        Raises:
            PermissionError: If user cannot update
            ValueError: If document not found
            RuntimeError: If saga fails
        """
        logger.info(f"Updating document: {doc_uuid} by user: {user_id}")

        # Check write access
        if self._acl:
            from src.services.acl_service import Permission

            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.WRITE,
            )
            if not has_access:
                raise PermissionError(
                    f"User {user_id} does not have write access to document {doc_uuid}"
                )

        # Get existing document
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            raise ValueError(f"Document not found: {doc_uuid}")

        # Prepare updates
        updates: dict[str, Any] = {}
        if request.title is not None:
            updates["title"] = request.title
        if request.status is not None:
            updates["status"] = request.status
        if request.security_level is not None:
            updates["security_level"] = request.security_level

        content_changed = request.content is not None

        if content_changed:
            # Content changed - need to regenerate chunks via saga
            content = request.content.strip()  # type: ignore
            if not content:
                raise ValueError("Document content cannot be empty")

            # Get next version
            next_version_no = await self._postgres_repo.get_next_version_no(doc_uuid)
            version_id = str(uuid4())

            # Create new chunks
            chunks = self._create_chunks(
                doc_uuid=doc_uuid,
                version_id=version_id,
                content=content,
            )

            if not chunks:
                raise ValueError("No chunks created from content")

            # Build saga objects
            content_hash = self._compute_content_hash(content)
            now = datetime.utcnow()

            document_data = {
                "doc_uuid": doc_uuid,
                "title": request.title or doc.title,
                "source": doc.source,
                "source_url": doc.source_url,
                "owner_id": doc.owner_id,
                "owner_org": doc.owner_org,
                "status": request.status or doc.status,
                "security_level": request.security_level or doc.security_level,
                "updated_at": now,
            }

            version_data = {
                "version_id": version_id,
                "doc_uuid": doc_uuid,
                "version_no": next_version_no,
                "content_hash": content_hash,
                "content_size": len(content.encode("utf-8")),
                "effective_from": now,
                "created_at": now,
            }

            class DocumentForSaga:
                def __init__(self, data: dict[str, Any], version: dict[str, Any]) -> None:
                    self.doc_uuid = data["doc_uuid"]
                    self.title = data["title"]
                    self.source = data["source"]
                    self.source_url = data["source_url"]
                    self.owner_id = data["owner_id"]
                    self.owner_org = data["owner_org"]
                    self.status = data["status"]
                    self.security_level = data["security_level"]
                    self.updated_at = data["updated_at"]
                    self.version = version

            class ChunkForSaga:
                def __init__(self, data: ChunkData) -> None:
                    self.chunk_uuid = data.chunk_uuid
                    self.doc_uuid = data.doc_uuid
                    self.version_id = data.version_id
                    self.chunk_no = data.chunk_no
                    self.chunk_text = data.chunk_text
                    self.char_start = data.char_start
                    self.char_end = data.char_end

            doc_obj = DocumentForSaga(document_data, version_data)
            chunk_objs = [ChunkForSaga(c) for c in chunks]

            # Execute update saga
            logger.info(f"Executing update saga for document: {doc_uuid}")
            result = await self._saga.execute_update_saga(
                doc_uuid=doc_uuid,
                document=doc_obj,
                chunks=chunk_objs,
            )

            if not result.success:
                logger.error(f"Update saga failed: {result.error}")
                raise RuntimeError(f"Failed to update document: {result.error}")

            chunk_count = len(chunks)
        else:
            # No content change - just update PostgreSQL
            if updates:
                await self._postgres_repo.update_document(doc_uuid, updates)

            # Get current chunk count
            chunks_list = await self._postgres_repo.get_chunks_by_doc(doc_uuid)
            chunk_count = len(chunks_list) if chunks_list else 0

        # Publish Kafka event
        if self._kafka:
            try:
                await self._kafka.send(
                    "document.updated",
                    {
                        "doc_uuid": doc_uuid,
                        "title": request.title or doc.title,
                        "updated_by": user_id,
                        "content_changed": content_changed,
                        "updated_at": datetime.utcnow().isoformat(),
                    },
                )
                logger.info(f"Published document.updated event: {doc_uuid}")
            except Exception as e:
                logger.warning(f"Failed to publish Kafka event: {e}")

        # Get updated document
        updated_doc = await self._postgres_repo.get_document(doc_uuid)
        if not updated_doc:
            raise RuntimeError(f"Document not found after update: {doc_uuid}")

        logger.info(f"Document updated successfully: {doc_uuid}")

        return DocumentResponse(
            doc_uuid=str(updated_doc.doc_uuid),
            title=updated_doc.title,
            owner_id=updated_doc.owner_id,
            owner_org=updated_doc.owner_org,
            source=updated_doc.source,
            source_url=updated_doc.source_url,
            status=updated_doc.status,
            security_level=updated_doc.security_level,
            chunk_count=chunk_count,
            created_at=updated_doc.created_at,
            updated_at=updated_doc.updated_at,
            metadata={},
        )

    # =========================================================================
    # Delete Document
    # =========================================================================

    async def delete_document(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> bool:
        """Delete a document.

        Removes document from all stores via saga.

        Args:
            doc_uuid: Document UUID
            user_id: User performing deletion
            user_groups: User's groups

        Returns:
            True if deleted

        Raises:
            PermissionError: If user cannot delete
            ValueError: If document not found
            RuntimeError: If saga fails
        """
        logger.info(f"Deleting document: {doc_uuid} by user: {user_id}")

        # Check admin access
        if self._acl:
            from src.services.acl_service import Permission

            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.ADMIN,
            )
            if not has_access:
                raise PermissionError(
                    f"User {user_id} does not have admin access to document {doc_uuid}"
                )

        # Check document exists
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            raise ValueError(f"Document not found: {doc_uuid}")

        # Execute delete saga
        logger.info(f"Executing delete saga for document: {doc_uuid}")
        result = await self._saga.execute_delete_saga(doc_uuid)

        if not result.success:
            logger.error(f"Delete saga failed: {result.error}")
            raise RuntimeError(f"Failed to delete document: {result.error}")

        # Publish Kafka event
        if self._kafka:
            try:
                await self._kafka.send(
                    "document.deleted",
                    {
                        "doc_uuid": doc_uuid,
                        "title": doc.title,
                        "deleted_by": user_id,
                        "deleted_at": datetime.utcnow().isoformat(),
                    },
                )
                logger.info(f"Published document.deleted event: {doc_uuid}")
            except Exception as e:
                logger.warning(f"Failed to publish Kafka event: {e}")

        logger.info(f"Document deleted successfully: {doc_uuid}")
        return True


# =============================================================================
# Singleton Factory
# =============================================================================

_service: DocumentService | None = None


def get_document_service(
    postgres_repo: Any | None = None,
    saga_coordinator: Any | None = None,
    embedding_service: Any | None = None,
    kafka_producer: KafkaProducerProtocol | None = None,
    acl_service: Any | None = None,
) -> DocumentService:
    """Get or create document service singleton.

    Args:
        postgres_repo: PostgreSQL repository (required on first call)
        saga_coordinator: Saga coordinator (required on first call)
        embedding_service: Embedding service (required on first call)
        kafka_producer: Kafka producer (optional)
        acl_service: ACL service (optional)

    Returns:
        DocumentService instance

    Raises:
        ValueError: If required dependencies not provided on first call
    """
    global _service
    if _service is None:
        if postgres_repo is None or saga_coordinator is None or embedding_service is None:
            raise ValueError(
                "postgres_repo, saga_coordinator, and embedding_service required "
                "for first initialization"
            )
        _service = DocumentService(
            postgres_repo=postgres_repo,
            saga_coordinator=saga_coordinator,
            embedding_service=embedding_service,
            kafka_producer=kafka_producer,
            acl_service=acl_service,
        )
    return _service


def set_document_service(service: DocumentService) -> None:
    """Set document service singleton.

    Args:
        service: DocumentService instance to set
    """
    global _service
    _service = service


def reset_document_service() -> None:
    """Reset document service singleton (for testing)."""
    global _service
    _service = None
