"""Neo4j repository for graph operations.

This module provides a data access layer for Neo4j graph database:
- Document Node CRUD
- Chunk Node CRUD
- Relationship management (CONTAINS, WROTE, MENTIONS)
- Graph search operations
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.domain.graph import ChunkNode, DocumentNode, Entity, GraphSearchResult

if TYPE_CHECKING:
    from src.infrastructure.database.neo4j import Neo4jClient


class Neo4jRepository:
    """Neo4j data access layer for graph operations.

    This repository provides:
    - Document and Chunk node management
    - Relationship creation and management
    - Graph-based search operations

    Example:
        >>> from src.infrastructure.database import get_neo4j_client
        >>> from src.repositories.neo4j import get_neo4j_repository
        >>>
        >>> client = get_neo4j_client()
        >>> await client.connect()
        >>> repo = get_neo4j_repository(client)
        >>>
        >>> # Create document node
        >>> doc = DocumentNode(doc_uuid="doc-1", title="Test", source="wiki")
        >>> await repo.create_document_node(doc)
    """

    def __init__(self, client: Neo4jClient) -> None:
        """Initialize repository.

        Args:
            client: Neo4j client instance
        """
        self._client = client

    @property
    def client(self) -> Neo4jClient:
        """Get underlying Neo4j client."""
        return self._client

    # =========================================================================
    # Document Node CRUD
    # =========================================================================

    async def create_document_node(self, doc: DocumentNode) -> str:
        """Create a document node.

        Uses MERGE to avoid duplicates.

        Args:
            doc: Document node data

        Returns:
            Created node's doc_uuid
        """
        query = """
            MERGE (d:Document {doc_uuid: $doc_uuid})
            SET d.title = $title,
                d.source = $source,
                d.security_level = $security_level,
                d.created_at = datetime()
            RETURN d.doc_uuid as doc_uuid
        """
        result = await self._client.execute_write(
            query,
            {
                "doc_uuid": doc.doc_uuid,
                "title": doc.title,
                "source": doc.source,
                "security_level": doc.security_level,
            },
        )
        return result[0]["doc_uuid"] if result else doc.doc_uuid

    async def get_document_node(self, doc_uuid: str) -> dict[str, Any] | None:
        """Get document node by UUID.

        Args:
            doc_uuid: Document UUID

        Returns:
            Document node properties or None if not found
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            RETURN d {.*} as doc
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return result[0]["doc"] if result else None

    async def update_document_node(
        self,
        doc_uuid: str,
        updates: dict[str, Any],
    ) -> bool:
        """Update document node properties.

        Args:
            doc_uuid: Document UUID
            updates: Properties to update

        Returns:
            True if updated, False if node not found
        """
        if not updates:
            return True

        set_clauses = ", ".join(f"d.{key} = ${key}" for key in updates)
        query = f"""
            MATCH (d:Document {{doc_uuid: $doc_uuid}})
            SET {set_clauses}
            RETURN d.doc_uuid as doc_uuid
        """
        params = {"doc_uuid": doc_uuid, **updates}
        result = await self._client.execute_write(query, params)
        return len(result) > 0

    async def delete_document_graph(self, doc_uuid: str) -> int:
        """Delete document and all related nodes/relationships.

        Performs cascade delete of document and its chunks.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted nodes
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            OPTIONAL MATCH (d)-[:CONTAINS]->(c:Chunk)
            WITH d, collect(c) as chunks
            DETACH DELETE d
            WITH chunks
            UNWIND chunks as chunk
            DETACH DELETE chunk
            RETURN count(*) as deleted_count
        """
        result = await self._client.execute_write(query, {"doc_uuid": doc_uuid})
        return result[0]["deleted_count"] if result else 0

    async def document_exists(self, doc_uuid: str) -> bool:
        """Check if document node exists.

        Args:
            doc_uuid: Document UUID

        Returns:
            True if document exists
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            RETURN count(d) > 0 as exists
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return result[0]["exists"] if result else False

    async def list_documents(
        self,
        source: str | None = None,
        security_level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List document nodes with optional filters.

        Args:
            source: Filter by source
            security_level: Filter by security level
            limit: Maximum results
            offset: Skip count

        Returns:
            List of document node properties
        """
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if source:
            conditions.append("d.source = $source")
            params["source"] = source

        if security_level:
            conditions.append("d.security_level = $security_level")
            params["security_level"] = security_level

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        query = f"""
            MATCH (d:Document)
            {where_clause}
            RETURN d {{.*}} as doc
            ORDER BY d.created_at DESC
            SKIP $offset
            LIMIT $limit
        """
        result = await self._client.execute_read(query, params)
        return [r["doc"] for r in result]

    # =========================================================================
    # Chunk Node CRUD
    # =========================================================================

    async def create_chunk_nodes(self, chunks: list[ChunkNode]) -> list[str]:
        """Create multiple chunk nodes in batch.

        Uses UNWIND for efficient batch insert.

        Args:
            chunks: List of chunk nodes

        Returns:
            List of created chunk UUIDs
        """
        if not chunks:
            return []

        query = """
            UNWIND $chunks as chunk
            MERGE (c:Chunk {chunk_uuid: chunk.chunk_uuid})
            SET c.sequence = chunk.sequence,
                c.text_preview = chunk.text_preview,
                c.section_path = chunk.section_path,
                c.doc_uuid = chunk.doc_uuid,
                c.created_at = datetime()
            RETURN c.chunk_uuid as chunk_uuid
        """

        chunk_data = [
            {
                "chunk_uuid": c.chunk_uuid,
                "doc_uuid": c.doc_uuid,
                "sequence": c.sequence,
                "text_preview": c.text_preview[:500],  # Limit preview length
                "section_path": c.section_path or "",
            }
            for c in chunks
        ]

        result = await self._client.execute_write(query, {"chunks": chunk_data})
        return [r["chunk_uuid"] for r in result]

    async def get_chunk_node(self, chunk_uuid: str) -> dict[str, Any] | None:
        """Get chunk node by UUID.

        Args:
            chunk_uuid: Chunk UUID

        Returns:
            Chunk node properties or None
        """
        query = """
            MATCH (c:Chunk {chunk_uuid: $chunk_uuid})
            RETURN c {.*} as chunk
        """
        result = await self._client.execute_read(query, {"chunk_uuid": chunk_uuid})
        return result[0]["chunk"] if result else None

    async def get_chunks_by_doc(self, doc_uuid: str) -> list[dict[str, Any]]:
        """Get all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of chunk node properties ordered by sequence
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})-[:CONTAINS]->(c:Chunk)
            RETURN c {.*} as chunk
            ORDER BY c.sequence
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return [r["chunk"] for r in result]

    async def delete_chunks_by_doc(self, doc_uuid: str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted chunks
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})-[:CONTAINS]->(c:Chunk)
            DETACH DELETE c
            RETURN count(c) as deleted_count
        """
        result = await self._client.execute_write(query, {"doc_uuid": doc_uuid})
        return result[0]["deleted_count"] if result else 0

    # =========================================================================
    # Relationships
    # =========================================================================

    async def create_contains_edges(
        self,
        doc_uuid: str,
        chunk_uuids: list[str],
    ) -> int:
        """Create CONTAINS relationships from document to chunks.

        Args:
            doc_uuid: Document UUID
            chunk_uuids: List of chunk UUIDs

        Returns:
            Number of relationships created
        """
        if not chunk_uuids:
            return 0

        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            UNWIND $chunk_uuids as chunk_uuid
            MATCH (c:Chunk {chunk_uuid: chunk_uuid})
            MERGE (d)-[r:CONTAINS]->(c)
            SET r.sequence = c.sequence
            RETURN count(r) as created
        """
        result = await self._client.execute_write(
            query,
            {"doc_uuid": doc_uuid, "chunk_uuids": chunk_uuids},
        )
        return result[0]["created"] if result else 0

    async def create_wrote_edge(
        self,
        person_id: str,
        doc_uuid: str,
        created_at: str | None = None,
    ) -> bool:
        """Create WROTE relationship from person to document.

        Args:
            person_id: Person emp_id
            doc_uuid: Document UUID
            created_at: Creation timestamp (optional)

        Returns:
            True if relationship created
        """
        query = """
            MATCH (p:Person {emp_id: $person_id})
            MATCH (d:Document {doc_uuid: $doc_uuid})
            MERGE (p)-[r:WROTE]->(d)
            SET r.created_at = coalesce($created_at, datetime())
            RETURN type(r) as rel_type
        """
        result = await self._client.execute_write(
            query,
            {"person_id": person_id, "doc_uuid": doc_uuid, "created_at": created_at},
        )
        return len(result) > 0

    async def create_mentions_edges(
        self,
        chunk_uuid: str,
        entities: list[Entity],
    ) -> int:
        """Create MENTIONS relationships from chunk to entities.

        Supports Person and Organization entities.

        Args:
            chunk_uuid: Chunk UUID
            entities: List of mentioned entities

        Returns:
            Number of relationships created
        """
        if not entities:
            return 0

        total_created = 0

        # Handle Person entities
        person_entities = [e for e in entities if e.entity_type == "Person"]
        if person_entities:
            person_query = """
                MATCH (c:Chunk {chunk_uuid: $chunk_uuid})
                UNWIND $persons as person
                MATCH (p:Person {emp_id: person.entity_id})
                MERGE (c)-[r:MENTIONS]->(p)
                SET r.confidence = person.confidence
                RETURN count(r) as created
            """
            person_data = [
                {"entity_id": e.entity_id, "confidence": e.confidence}
                for e in person_entities
            ]
            result = await self._client.execute_write(
                person_query,
                {"chunk_uuid": chunk_uuid, "persons": person_data},
            )
            total_created += result[0]["created"] if result else 0

        # Handle Organization entities
        org_entities = [e for e in entities if e.entity_type == "Organization"]
        if org_entities:
            org_query = """
                MATCH (c:Chunk {chunk_uuid: $chunk_uuid})
                UNWIND $orgs as org
                MATCH (o:Organization {org_id: org.entity_id})
                MERGE (c)-[r:MENTIONS]->(o)
                SET r.confidence = org.confidence
                RETURN count(r) as created
            """
            org_data = [
                {"entity_id": e.entity_id, "confidence": e.confidence}
                for e in org_entities
            ]
            result = await self._client.execute_write(
                org_query,
                {"chunk_uuid": chunk_uuid, "orgs": org_data},
            )
            total_created += result[0]["created"] if result else 0

        return total_created

    async def get_document_author(self, doc_uuid: str) -> dict[str, Any] | None:
        """Get author of a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Person node properties or None
        """
        query = """
            MATCH (p:Person)-[:WROTE]->(d:Document {doc_uuid: $doc_uuid})
            RETURN p {.*} as person
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return result[0]["person"] if result else None

    async def get_chunk_mentions(self, chunk_uuid: str) -> list[dict[str, Any]]:
        """Get entities mentioned in a chunk.

        Args:
            chunk_uuid: Chunk UUID

        Returns:
            List of entity properties with relationship info
        """
        query = """
            MATCH (c:Chunk {chunk_uuid: $chunk_uuid})-[r:MENTIONS]->(e)
            RETURN labels(e)[0] as entity_type,
                   e {.*} as entity,
                   r.confidence as confidence
        """
        result = await self._client.execute_read(query, {"chunk_uuid": chunk_uuid})
        return result

    # =========================================================================
    # Graph Search
    # =========================================================================

    async def graph_search(
        self,
        query: str,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
    ) -> list[GraphSearchResult]:
        """Search chunks by keyword in text_preview.

        Uses case-insensitive CONTAINS for keyword matching.

        Args:
            query: Search query (keywords)
            doc_uuids: Allowed document UUIDs (ACL filter)
            top_k: Maximum results

        Returns:
            List of search results
        """
        acl_filter = ""
        params: dict[str, Any] = {"query": query.lower(), "top_k": top_k}

        if doc_uuids is not None:
            if not doc_uuids:
                # Empty list means no access
                return []
            acl_filter = "AND d.doc_uuid IN $doc_uuids"
            params["doc_uuids"] = doc_uuids

        cypher = f"""
            MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
            WHERE toLower(c.text_preview) CONTAINS $query
            {acl_filter}
            RETURN
                c.chunk_uuid as chunk_uuid,
                d.doc_uuid as doc_uuid,
                d.title as title,
                c.text_preview as text_preview,
                c.section_path as section_path,
                1.0 as score
            ORDER BY c.sequence
            LIMIT $top_k
        """

        result = await self._client.execute_read(cypher, params)
        return [GraphSearchResult.from_record(r) for r in result]

    async def graph_search_with_context(
        self,
        query: str,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
    ) -> list[GraphSearchResult]:
        """Search with relationship context.

        Finds chunks matching query and includes related entities.

        Args:
            query: Search query
            doc_uuids: Allowed document UUIDs
            top_k: Maximum results

        Returns:
            List of search results with related entities
        """
        acl_filter = ""
        params: dict[str, Any] = {"query": query.lower(), "top_k": top_k}

        if doc_uuids is not None:
            if not doc_uuids:
                return []
            acl_filter = "AND d.doc_uuid IN $doc_uuids"
            params["doc_uuids"] = doc_uuids

        cypher = f"""
            MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
            WHERE toLower(c.text_preview) CONTAINS $query
            {acl_filter}
            OPTIONAL MATCH (c)-[:MENTIONS]->(e)
            WITH d, c, collect(DISTINCT coalesce(e.name, e.emp_id, '')) as entities
            RETURN
                c.chunk_uuid as chunk_uuid,
                d.doc_uuid as doc_uuid,
                d.title as title,
                c.text_preview as text_preview,
                c.section_path as section_path,
                1.0 as score,
                [x IN entities WHERE x <> ''] as related_entities
            ORDER BY size(entities) DESC, c.sequence
            LIMIT $top_k
        """

        result = await self._client.execute_read(cypher, params)
        return [GraphSearchResult.from_record(r) for r in result]

    async def find_related_documents(
        self,
        doc_uuid: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find documents related through shared entities.

        Args:
            doc_uuid: Source document UUID
            limit: Maximum results

        Returns:
            List of related documents with shared entity info
        """
        cypher = """
            MATCH (d1:Document {doc_uuid: $doc_uuid})-[:CONTAINS]->(c1:Chunk)
            MATCH (c1)-[:MENTIONS]->(e)<-[:MENTIONS]-(c2:Chunk)<-[:CONTAINS]-(d2:Document)
            WHERE d1 <> d2
            WITH d2, e, count(DISTINCT c2) as shared_chunks
            RETURN
                d2.doc_uuid as doc_uuid,
                d2.title as title,
                collect(DISTINCT e.name)[0..5] as shared_entities,
                sum(shared_chunks) as relevance_score
            ORDER BY relevance_score DESC
            LIMIT $limit
        """

        result = await self._client.execute_read(
            cypher,
            {"doc_uuid": doc_uuid, "limit": limit},
        )
        return result

    async def get_document_graph(
        self,
        doc_uuid: str,
    ) -> dict[str, Any]:
        """Get full graph for a document.

        Returns document, chunks, and all relationships.

        Args:
            doc_uuid: Document UUID

        Returns:
            Dictionary with document, chunks, and relationships
        """
        # Get document
        doc = await self.get_document_node(doc_uuid)
        if not doc:
            return {"document": None, "chunks": [], "relationships": []}

        # Get chunks with relationships
        chunks_query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})-[r:CONTAINS]->(c:Chunk)
            OPTIONAL MATCH (c)-[m:MENTIONS]->(e)
            RETURN
                c {.*} as chunk,
                collect(DISTINCT {type: labels(e)[0], name: coalesce(e.name, e.emp_id)}) as mentions
            ORDER BY c.sequence
        """
        chunks_result = await self._client.execute_read(
            chunks_query, {"doc_uuid": doc_uuid}
        )

        # Get author
        author = await self.get_document_author(doc_uuid)

        return {
            "document": doc,
            "author": author,
            "chunks": [
                {**r["chunk"], "mentions": r["mentions"]}
                for r in chunks_result
            ],
        }


# =============================================================================
# Singleton Factory
# =============================================================================

_repository: Neo4jRepository | None = None


def get_neo4j_repository(client: Neo4jClient | None = None) -> Neo4jRepository:
    """Get or create Neo4j repository singleton.

    Args:
        client: Neo4j client (required on first call,
                or auto-loaded from infrastructure)

    Returns:
        Neo4jRepository instance
    """
    global _repository
    if _repository is None:
        if client is None:
            from src.infrastructure.database import get_neo4j_client

            client = get_neo4j_client()
        _repository = Neo4jRepository(client)
    return _repository


def reset_neo4j_repository() -> None:
    """Reset the repository singleton (for testing)."""
    global _repository
    _repository = None
