# Task Execution Plan: 2.2.3 - Neo4j Repository 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.2.3 |
| **Task Name** | Neo4j Repository 구현 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 2.1.3 |

### Description
Neo4j 그래프 데이터 접근 레이어를 구현합니다.

### Acceptance Criteria
- [ ] `src/repositories/neo4j/repository.py` 생성
- [ ] Document Node CRUD 메서드
- [ ] Chunk Node CRUD 메서드
- [ ] Relationship 생성 메서드 (CONTAINS, WROTE, MENTIONS)
- [ ] Graph Search 메서드

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.3 Repository Layer
- **Schema**: `docs/architecture/architecture.md` Section 6.3 Neo4j Graph Schema

### 2.2 Node Labels & Relationships
```
Node Labels:
  - Document {doc_uuid, title, source, security_level}
  - Chunk {chunk_uuid, sequence, text_preview, section_path}
  - Person {emp_id, name, department}
  - Organization {org_id, name}

Relationships:
  - (Document)-[:CONTAINS {sequence}]->(Chunk)
  - (Person)-[:WROTE {created_at}]->(Document)
  - (Chunk)-[:MENTIONS {confidence}]->(Entity)
```

### 2.3 설계 결정
1. **Async Queries**: Neo4jClient의 execute_read/write 활용
2. **Batch Operations**: UNWIND로 대량 노드 생성
3. **Cascade Delete**: 문서 삭제 시 관련 청크도 삭제
4. **Text Search**: text_preview CONTAINS로 키워드 검색

### 2.4 클래스 구조
```
Neo4jRepository
├── __init__(client: Neo4jClient)
├── Document Node
│   ├── create_document_node(doc) -> str
│   ├── get_document_node(doc_uuid) -> dict | None
│   └── delete_document_graph(doc_uuid) -> int
├── Chunk Nodes
│   ├── create_chunk_nodes(chunks) -> list[str]
│   └── get_chunks_by_doc(doc_uuid) -> list[dict]
├── Relationships
│   ├── create_contains_edges(doc_uuid, chunk_uuids) -> None
│   ├── create_wrote_edge(person_id, doc_uuid) -> None
│   └── create_mentions_edges(chunk_uuid, entities) -> None
└── Search
    ├── graph_search(query, doc_uuids, top_k) -> list[GraphSearchResult]
    └── find_related_documents(doc_uuid, hops) -> list[dict]
```

---

## 3. Implementation Steps

### Step 1: Domain Models 및 기본 구조 (1h)

**작업 내용:**
1. GraphSearchResult 데이터 클래스
2. DocumentNode, ChunkNode 클래스
3. Repository 기본 구조

**src/domain/graph.py:**
```python
"""Graph-related domain models."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentNode:
    """Document node for Neo4j."""

    doc_uuid: str
    title: str
    source: str
    security_level: str = "internal"
    created_at: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkNode:
    """Chunk node for Neo4j."""

    chunk_uuid: str
    doc_uuid: str
    sequence: int
    text_preview: str  # First 500 chars for search
    section_path: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Entity:
    """Entity mentioned in chunk."""

    entity_type: str  # Person, Organization, Project, Policy
    entity_id: str
    name: str
    confidence: float = 1.0


@dataclass
class GraphSearchResult:
    """Graph search result."""

    chunk_uuid: str
    doc_uuid: str
    title: str
    text_preview: str
    section_path: str | None
    score: float
    path_length: int = 0
    related_entities: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: dict) -> "GraphSearchResult":
        """Create from Neo4j record."""
        return cls(
            chunk_uuid=record.get("chunk_uuid", ""),
            doc_uuid=record.get("doc_uuid", ""),
            title=record.get("title", ""),
            text_preview=record.get("text_preview", ""),
            section_path=record.get("section_path"),
            score=record.get("score", 0.0),
            path_length=record.get("path_length", 0),
            related_entities=record.get("related_entities", []),
        )
```

**src/repositories/neo4j/repository.py:**
```python
"""Neo4j repository for graph operations."""
from typing import Any

from src.domain.graph import DocumentNode, ChunkNode, Entity, GraphSearchResult
from src.infrastructure.database.neo4j import Neo4jClient


class Neo4jRepository:
    """Neo4j data access layer for graph operations."""

    def __init__(self, client: Neo4jClient) -> None:
        """Initialize repository.

        Args:
            client: Neo4j client
        """
        self._client = client
```

**완료 기준:**
- [ ] Domain 모델 정의
- [ ] Repository 기본 구조

---

### Step 2: Document Node CRUD 구현 (1h)

**작업 내용:**
1. create_document_node
2. get_document_node
3. delete_document_graph

**src/repositories/neo4j/repository.py (계속):**
```python
    # ==================
    # Document Node CRUD
    # ==================

    async def create_document_node(self, doc: DocumentNode) -> str:
        """Create a document node.

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
            Document node properties or None
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
            True if updated
        """
        if not updates:
            return True

        set_clauses = ", ".join(f"d.{key} = ${key}" for key in updates.keys())
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

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted nodes
        """
        # Delete document and all connected chunks
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            OPTIONAL MATCH (d)-[:CONTAINS]->(c:Chunk)
            DETACH DELETE d, c
            RETURN count(d) + count(c) as deleted_count
        """
        result = await self._client.execute_write(query, {"doc_uuid": doc_uuid})
        return result[0]["deleted_count"] if result else 0

    async def document_exists(self, doc_uuid: str) -> bool:
        """Check if document node exists.

        Args:
            doc_uuid: Document UUID

        Returns:
            True if exists
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})
            RETURN count(d) > 0 as exists
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return result[0]["exists"] if result else False
```

**완료 기준:**
- [ ] create_document_node 구현
- [ ] get_document_node 구현
- [ ] update_document_node 구현
- [ ] delete_document_graph 구현

---

### Step 3: Chunk Nodes 및 Relationships 구현 (2h)

**작업 내용:**
1. create_chunk_nodes (배치)
2. create_contains_edges
3. create_wrote_edge
4. create_mentions_edges

**src/repositories/neo4j/repository.py (계속):**
```python
    # ==================
    # Chunk Node CRUD
    # ==================

    async def create_chunk_nodes(self, chunks: list[ChunkNode]) -> list[str]:
        """Create multiple chunk nodes in batch.

        Args:
            chunks: List of chunk nodes

        Returns:
            List of created chunk UUIDs
        """
        if not chunks:
            return []

        # Use UNWIND for batch insert
        query = """
            UNWIND $chunks as chunk
            MERGE (c:Chunk {chunk_uuid: chunk.chunk_uuid})
            SET c.sequence = chunk.sequence,
                c.text_preview = chunk.text_preview,
                c.section_path = chunk.section_path,
                c.created_at = datetime()
            RETURN c.chunk_uuid as chunk_uuid
        """

        chunk_data = [
            {
                "chunk_uuid": c.chunk_uuid,
                "sequence": c.sequence,
                "text_preview": c.text_preview[:500],  # Limit preview length
                "section_path": c.section_path or "",
            }
            for c in chunks
        ]

        result = await self._client.execute_write(query, {"chunks": chunk_data})
        return [r["chunk_uuid"] for r in result]

    async def get_chunks_by_doc(self, doc_uuid: str) -> list[dict[str, Any]]:
        """Get all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of chunk node properties
        """
        query = """
            MATCH (d:Document {doc_uuid: $doc_uuid})-[:CONTAINS]->(c:Chunk)
            RETURN c {.*} as chunk
            ORDER BY c.sequence
        """
        result = await self._client.execute_read(query, {"doc_uuid": doc_uuid})
        return [r["chunk"] for r in result]

    # ==================
    # Relationships
    # ==================

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
            created_at: Creation timestamp

        Returns:
            True if created
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

        Args:
            chunk_uuid: Chunk UUID
            entities: List of mentioned entities

        Returns:
            Number of relationships created
        """
        if not entities:
            return 0

        # Group by entity type for efficient processing
        query = """
            MATCH (c:Chunk {chunk_uuid: $chunk_uuid})
            UNWIND $entities as entity
            CALL {
                WITH c, entity
                MATCH (e)
                WHERE labels(e)[0] = entity.type
                AND e[$id_field] = entity.entity_id
                MERGE (c)-[r:MENTIONS]->(e)
                SET r.confidence = entity.confidence
                RETURN r
            }
            RETURN count(*) as created
        """

        # This is simplified; actual implementation would handle different entity types
        entity_data = [
            {
                "type": e.entity_type,
                "entity_id": e.entity_id,
                "confidence": e.confidence,
            }
            for e in entities
        ]

        # For now, handle Person entities specifically
        person_query = """
            MATCH (c:Chunk {chunk_uuid: $chunk_uuid})
            UNWIND $persons as person
            MATCH (p:Person {emp_id: person.entity_id})
            MERGE (c)-[r:MENTIONS]->(p)
            SET r.confidence = person.confidence
            RETURN count(r) as created
        """

        persons = [e for e in entity_data if e["type"] == "Person"]
        if persons:
            result = await self._client.execute_write(
                person_query,
                {"chunk_uuid": chunk_uuid, "persons": persons},
            )
            return result[0]["created"] if result else 0

        return 0
```

**완료 기준:**
- [ ] create_chunk_nodes 구현
- [ ] get_chunks_by_doc 구현
- [ ] create_contains_edges 구현
- [ ] create_wrote_edge 구현
- [ ] create_mentions_edges 구현

---

### Step 4: Graph Search 구현 (1h)

**작업 내용:**
1. graph_search - 키워드 기반 그래프 탐색
2. find_related_documents - 관계 기반 추천

**src/repositories/neo4j/repository.py (계속):**
```python
    # ==================
    # Graph Search
    # ==================

    async def graph_search(
        self,
        query: str,
        doc_uuids: list[str] | None = None,
        top_k: int = 10,
    ) -> list[GraphSearchResult]:
        """Search chunks by keyword in text_preview.

        Args:
            query: Search query (keywords)
            doc_uuids: Allowed document UUIDs (ACL filter)
            top_k: Max results

        Returns:
            List of search results
        """
        # Build ACL filter
        acl_filter = ""
        params: dict[str, Any] = {"query": query.lower(), "top_k": top_k}

        if doc_uuids:
            acl_filter = "AND d.doc_uuid IN $doc_uuids"
            params["doc_uuids"] = doc_uuids

        # Search query using CONTAINS for simple keyword matching
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
        context_hops: int = 1,
    ) -> list[GraphSearchResult]:
        """Search with relationship context.

        Finds chunks matching query and includes related entities.

        Args:
            query: Search query
            doc_uuids: Allowed document UUIDs
            top_k: Max results
            context_hops: Number of relationship hops for context

        Returns:
            List of search results with related entities
        """
        acl_filter = ""
        params: dict[str, Any] = {"query": query.lower(), "top_k": top_k}

        if doc_uuids:
            acl_filter = "AND d.doc_uuid IN $doc_uuids"
            params["doc_uuids"] = doc_uuids

        cypher = f"""
            MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
            WHERE toLower(c.text_preview) CONTAINS $query
            {acl_filter}
            OPTIONAL MATCH (c)-[:MENTIONS]->(e)
            WITH d, c, collect(DISTINCT labels(e)[0] + ':' + coalesce(e.name, e.emp_id, '')) as entities
            RETURN
                c.chunk_uuid as chunk_uuid,
                d.doc_uuid as doc_uuid,
                d.title as title,
                c.text_preview as text_preview,
                c.section_path as section_path,
                1.0 as score,
                entities as related_entities
            ORDER BY size(entities) DESC, c.sequence
            LIMIT $top_k
        """

        result = await self._client.execute_read(cypher, params)
        return [GraphSearchResult.from_record(r) for r in result]

    async def find_related_documents(
        self,
        doc_uuid: str,
        max_hops: int = 2,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find documents related through shared entities.

        Args:
            doc_uuid: Source document UUID
            max_hops: Maximum relationship hops
            limit: Max results

        Returns:
            List of related documents with relationship path
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
```

**완료 기준:**
- [ ] graph_search 구현
- [ ] graph_search_with_context 구현
- [ ] find_related_documents 구현

---

### Step 5: 테스트 작성 (1h)

**작업 내용:**
1. Node CRUD 테스트
2. Relationship 테스트
3. Search 테스트

**tests/unit/test_repositories/test_neo4j_repository.py:**
```python
"""Tests for Neo4j repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.repositories.neo4j.repository import Neo4jRepository
from src.domain.graph import DocumentNode, ChunkNode, GraphSearchResult


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock Neo4j client."""
    client = MagicMock()
    client.execute_read = AsyncMock(return_value=[])
    client.execute_write = AsyncMock(return_value=[])
    return client


@pytest.fixture
def repo(mock_client: MagicMock) -> Neo4jRepository:
    """Create repository with mock client."""
    return Neo4jRepository(mock_client)


class TestDocumentNode:
    """Tests for document node operations."""

    async def test_create_document_node(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test document node creation."""
        mock_client.execute_write.return_value = [{"doc_uuid": "doc-001"}]

        doc = DocumentNode(
            doc_uuid="doc-001",
            title="Test Document",
            source="wiki",
            security_level="internal",
        )

        result = await repo.create_document_node(doc)

        assert result == "doc-001"
        mock_client.execute_write.assert_called_once()

    async def test_get_document_node_found(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test getting existing document node."""
        mock_client.execute_read.return_value = [
            {"doc": {"doc_uuid": "doc-001", "title": "Test"}}
        ]

        result = await repo.get_document_node("doc-001")

        assert result is not None
        assert result["doc_uuid"] == "doc-001"

    async def test_get_document_node_not_found(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test getting non-existent document node."""
        mock_client.execute_read.return_value = []

        result = await repo.get_document_node("nonexistent")

        assert result is None

    async def test_delete_document_graph(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test document graph deletion."""
        mock_client.execute_write.return_value = [{"deleted_count": 5}]

        result = await repo.delete_document_graph("doc-001")

        assert result == 5


class TestChunkNodes:
    """Tests for chunk node operations."""

    async def test_create_chunk_nodes_batch(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test batch chunk creation."""
        mock_client.execute_write.return_value = [
            {"chunk_uuid": "chunk-001"},
            {"chunk_uuid": "chunk-002"},
        ]

        chunks = [
            ChunkNode(
                chunk_uuid="chunk-001",
                doc_uuid="doc-001",
                sequence=0,
                text_preview="First chunk",
            ),
            ChunkNode(
                chunk_uuid="chunk-002",
                doc_uuid="doc-001",
                sequence=1,
                text_preview="Second chunk",
            ),
        ]

        result = await repo.create_chunk_nodes(chunks)

        assert len(result) == 2
        mock_client.execute_write.assert_called_once()


class TestGraphSearch:
    """Tests for graph search operations."""

    async def test_graph_search(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test graph search."""
        mock_client.execute_read.return_value = [
            {
                "chunk_uuid": "chunk-001",
                "doc_uuid": "doc-001",
                "title": "Test Doc",
                "text_preview": "This is test content",
                "section_path": "/intro",
                "score": 1.0,
            }
        ]

        results = await repo.graph_search("test", doc_uuids=["doc-001"], top_k=10)

        assert len(results) == 1
        assert results[0].chunk_uuid == "chunk-001"

    async def test_graph_search_with_acl_filter(self, repo: Neo4jRepository, mock_client: MagicMock) -> None:
        """Test graph search with ACL filter."""
        mock_client.execute_read.return_value = []

        await repo.graph_search("test", doc_uuids=["doc-001", "doc-002"])

        call_args = mock_client.execute_read.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "doc_uuids" in params
        assert "IN $doc_uuids" in query
```

**완료 기준:**
- [ ] Document Node 테스트 작성
- [ ] Chunk Node 테스트 작성
- [ ] Graph Search 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_document_node` | 문서 노드 생성 | UUID 반환 |
| `test_get_document_node_*` | 문서 노드 조회 | 노드 또는 None |
| `test_delete_document_graph` | 문서 그래프 삭제 | 삭제 건수 |
| `test_create_chunk_nodes_batch` | 청크 배치 생성 | UUID 리스트 |
| `test_graph_search` | 그래프 검색 | 결과 리스트 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_document_lifecycle` | 문서 CRUD | 성공 |
| `test_relationship_creation` | 관계 생성 | 성공 |
| `test_graph_traversal` | 그래프 탐색 | 관련 문서 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Cypher Injection | High | Low | 파라미터화된 쿼리 |
| 대량 노드 생성 성능 | Medium | Medium | UNWIND 배치 처리 |
| N+1 쿼리 | Medium | Medium | 필요한 데이터만 조회 |

---

## 6. Definition of Done

- [ ] `src/repositories/neo4j/repository.py` 구현
- [ ] `src/domain/graph.py` 모델 정의
- [ ] Document Node CRUD 구현
- [ ] Chunk Node CRUD 구현
- [ ] Relationship 생성 메서드 구현
- [ ] Graph Search 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Domain Models | 1h | - |
| Step 2: Document Node CRUD | 1h | - |
| Step 3: Chunk & Relationships | 2h | - |
| Step 4: Graph Search | 1h | - |
| Step 5: 테스트 | 1h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
