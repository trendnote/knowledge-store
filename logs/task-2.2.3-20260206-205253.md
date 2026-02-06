# Task 2.2.3: Neo4j Repository 구현

## 작업 정보
- **Task ID**: 2.2.3
- **작업자**: Claude AI
- **작업일시**: 2026-02-06 20:52:53
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/16
- **Task Plan**: docs/task-plans/task-2.2.3-plan.md

## 작업 개요
Neo4j 그래프 데이터베이스를 위한 Repository 레이어를 구현하여 Document/Chunk 노드 관리, 관계 생성, 그래프 검색 기능을 제공합니다.

## 생성된 파일

### 1. Domain Models
**파일**: `src/domain/graph.py`

그래프 관련 도메인 모델:
- `DocumentNode`: Neo4j Document 노드
  - doc_uuid, title, source, security_level, created_at, properties
- `ChunkNode`: Neo4j Chunk 노드
  - chunk_uuid, doc_uuid, sequence, text_preview, section_path, properties
- `Entity`: 청크에서 언급된 엔티티
  - entity_type (Person/Organization), entity_id, name, confidence
- `GraphSearchResult`: 그래프 검색 결과
  - chunk_uuid, doc_uuid, title, text_preview, section_path, score
  - path_length, related_entities
  - `from_record()` 클래스 메서드

**exports 업데이트**: `src/domain/__init__.py`

### 2. Neo4j Repository
**파일**: `src/repositories/neo4j/repository.py`

#### Document Node CRUD
- `create_document_node(doc: DocumentNode) -> str`
- `get_document_node(doc_uuid: str) -> dict | None`
- `update_document_node(doc_uuid: str, updates: dict) -> bool`
- `delete_document_graph(doc_uuid: str) -> int`
  - Cascade delete: 문서 + 연결된 청크 모두 삭제
- `document_exists(doc_uuid: str) -> bool`
- `list_documents(source, security_level, limit, offset) -> list[dict]`

#### Chunk Node CRUD
- `create_chunk_nodes(chunks: list[ChunkNode]) -> list[str]`
  - UNWIND로 배치 삽입
  - text_preview 500자 제한
- `get_chunk_node(chunk_uuid: str) -> dict | None`
- `get_chunks_by_doc(doc_uuid: str) -> list[dict]`
- `delete_chunks_by_doc(doc_uuid: str) -> int`

#### Relationship Methods
- `create_contains_edges(doc_uuid, chunk_uuids) -> int`
  - Document -[:CONTAINS]-> Chunk
- `create_wrote_edge(person_id, doc_uuid, created_at) -> bool`
  - Person -[:WROTE]-> Document
- `create_mentions_edges(chunk_uuid, entities) -> int`
  - Chunk -[:MENTIONS]-> Entity (Person/Organization)
- `get_document_author(doc_uuid) -> dict | None`
- `get_chunk_mentions(chunk_uuid) -> list[dict]`

#### Graph Search Methods
- `graph_search(query, doc_uuids, top_k) -> list[GraphSearchResult]`
  - 키워드 기반 검색 (CONTAINS)
  - ACL 필터링 지원
- `graph_search_with_context(query, doc_uuids, top_k) -> list[GraphSearchResult]`
  - 관련 엔티티 포함
- `find_related_documents(doc_uuid, limit) -> list[dict]`
  - 공유 엔티티 기반 관련 문서 탐색
- `get_document_graph(doc_uuid) -> dict`
  - 문서 + 청크 + 관계 전체 그래프

#### Factory Pattern
- `get_neo4j_repository(client: Neo4jClient | None) -> Neo4jRepository`
- `reset_neo4j_repository() -> None`

**exports**: `src/repositories/neo4j/__init__.py`

### 3. Unit Tests
**파일**: `tests/unit/test_repositories/test_neo4j_repository.py`

테스트 클래스:
- `TestDocumentNodeCRUD`: 13개 테스트
- `TestChunkNodeCRUD`: 7개 테스트
- `TestRelationships`: 10개 테스트
- `TestGraphSearch`: 9개 테스트
- `TestGraphSearchResult`: 2개 테스트
- `TestSingleton`: 4개 테스트

**총 45개 테스트, 100% PASSED**

## 기술적 특징

### 1. MERGE for Upsert
```cypher
MERGE (d:Document {doc_uuid: $doc_uuid})
SET d.title = $title, d.source = $source
RETURN d.doc_uuid as doc_uuid
```

### 2. UNWIND for Batch Operations
```cypher
UNWIND $chunks as chunk
MERGE (c:Chunk {chunk_uuid: chunk.chunk_uuid})
SET c.sequence = chunk.sequence, c.text_preview = chunk.text_preview
RETURN c.chunk_uuid as chunk_uuid
```

### 3. Cascade Delete
```cypher
MATCH (d:Document {doc_uuid: $doc_uuid})
OPTIONAL MATCH (d)-[:CONTAINS]->(c:Chunk)
DETACH DELETE d, c
```

### 4. ACL Filter in Search
```python
if doc_uuids is not None:
    if not doc_uuids:
        return []  # Empty list = no access
    acl_filter = "AND d.doc_uuid IN $doc_uuids"
```

### 5. Entity Type Handling
```python
# Person entities
person_entities = [e for e in entities if e.entity_type == "Person"]
# Organization entities
org_entities = [e for e in entities if e.entity_type == "Organization"]
```

## 테스트 결과

```
============================== test session starts ==============================
45 passed, 6 warnings in 1.70s

Coverage:
- src/domain/graph.py: 100%
- src/repositories/neo4j/repository.py: 98%
```

## 해결된 이슈

### 1. Ruff Lint Error
- **문제**: `SIM118 Use 'key in dict' instead of 'key in dict.keys()'`
- **해결**: `for key in updates.keys()` → `for key in updates`

## 다음 단계
- Task 2.2.4: Kafka Repository 구현
