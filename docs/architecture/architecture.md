# Architecture: Knowledge Store Layer

---

## Meta
- **PRD Reference**: [knowledge-store-layer-prd.md](../prd/knowledge-store-layer-prd.md)
- **Tech Stack Reference**: [tech-stack.md](../tech-stack/tech-stack.md)
- **Status**: Draft
- **Last Updated**: 2026-01-25
- **Architect**: Platform Team

---

## 1. Executive Summary

Knowledge Store Layer는 **Tri-Store Architecture**를 구현하는 플랫폼 계층으로, Vector DB(Milvus), Graph DB(Neo4j), RDB(PostgreSQL)를 통합하여 Hybrid Search와 ACL 기반 권한 필터링을 제공합니다.

**핵심 아키텍처 결정:**
- **Layered Architecture**: API → Service → Repository → Infrastructure
- **Saga Pattern**: 3개 저장소 분산 트랜잭션 관리
- **Async-First**: 비동기 I/O 기반 병렬 검색
- **Event-Driven**: Kafka 기반 변경 동기화

---

## 2. System Context

### 2.1 Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Systems                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐       │
│  │  Data Ingestion  │    │  Orchestration   │    │    Platform      │       │
│  │     Layer        │    │     Layer        │    │    Operator      │       │
│  │  (Future Phase)  │    │  (Future Phase)  │    │                  │       │
│  └────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘       │
│           │                       │                       │                  │
│           │ POST /documents       │ POST /search          │ Monitoring       │
│           │                       │                       │                  │
│           ▼                       ▼                       ▼                  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                                                                        │  │
│  │                     KNOWLEDGE STORE LAYER                              │  │
│  │                                                                        │  │
│  │   ┌─────────────────────────────────────────────────────────────┐     │  │
│  │   │                      FastAPI Application                     │     │  │
│  │   └─────────────────────────────────────────────────────────────┘     │  │
│  │                                                                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│           │                       │                       │                  │
│           ▼                       ▼                       ▼                  │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐       │
│  │   PostgreSQL     │    │     Milvus       │    │     Neo4j        │       │
│  │   (Metadata)     │    │    (Vector)      │    │    (Graph)       │       │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘       │
│                                                                              │
│                          ┌──────────────────┐                               │
│                          │      Kafka       │                               │
│                          │  (Event Stream)  │                               │
│                          └──────────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 External Interfaces

| Interface | Direction | Protocol | Description |
|-----------|-----------|----------|-------------|
| Data Ingestion Layer | Inbound | REST API | 문서 저장 요청 |
| Orchestration Layer | Inbound | REST API | Hybrid Search 요청 |
| Platform Operator | Inbound | REST API | Health Check, Metrics |
| Kafka | Bidirectional | Kafka Protocol | 이벤트 발행/구독 |

---

## 3. High-Level Architecture

### 3.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE STORE LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         API LAYER (FastAPI)                          │    │
│  ├─────────────────────────────────────────────────────────────────────┤    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │  Document   │  │   Search    │  │   Health    │  │   Metrics   │ │    │
│  │  │   Router    │  │   Router    │  │   Router    │  │   Router    │ │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │    │
│  └─────────┼────────────────┼────────────────┼────────────────┼────────┘    │
│            │                │                │                │              │
│  ┌─────────┼────────────────┼────────────────┼────────────────┼────────┐    │
│  │         ▼                ▼                ▼                ▼         │    │
│  │                       SERVICE LAYER                                  │    │
│  ├──────────────────────────────────────────────────────────────────────┤    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │  Document   │  │   Search    │  │    ACL      │  │    Sync     │ │    │
│  │  │  Service    │  │   Service   │  │   Service   │  │   Service   │ │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │    │
│  │         │                │                │                │         │    │
│  │  ┌──────┴──────┐  ┌──────┴──────┐                                   │    │
│  │  │   Saga      │  │  Embedding  │                                   │    │
│  │  │ Coordinator │  │   Service   │                                   │    │
│  │  └─────────────┘  └─────────────┘                                   │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│            │                │                │                │              │
│  ┌─────────┼────────────────┼────────────────┼────────────────┼────────┐    │
│  │         ▼                ▼                ▼                ▼         │    │
│  │                     REPOSITORY LAYER                                 │    │
│  ├──────────────────────────────────────────────────────────────────────┤    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │  Postgres   │  │   Milvus    │  │   Neo4j     │  │   Kafka     │ │    │
│  │  │ Repository  │  │ Repository  │  │ Repository  │  │  Producer   │ │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │    │
│  └─────────┼────────────────┼────────────────┼────────────────┼────────┘    │
│            │                │                │                │              │
│  ┌─────────┼────────────────┼────────────────┼────────────────┼────────┐    │
│  │         ▼                ▼                ▼                ▼         │    │
│  │                   INFRASTRUCTURE LAYER                               │    │
│  ├──────────────────────────────────────────────────────────────────────┤    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │    │
│  │  │  asyncpg    │  │   pymilvus  │  │ neo4j-driver│  │  aiokafka   │ │    │
│  │  │   Client    │  │    Client   │  │    Client   │  │   Client    │ │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │    │
│  └─────────┼────────────────┼────────────────┼────────────────┼────────┘    │
│            │                │                │                │              │
└────────────┼────────────────┼────────────────┼────────────────┼──────────────┘
             │                │                │                │
             ▼                ▼                ▼                ▼
      ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
      │ PostgreSQL  │  │   Milvus    │  │    Neo4j    │  │    Kafka    │
      │   :5432     │  │   :19530    │  │    :7687    │  │    :9092    │
      └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

### 3.2 Layer Responsibilities

| Layer | Responsibility | Components |
|-------|----------------|------------|
| **API Layer** | HTTP 요청 처리, 검증, 응답 포맷팅 | Routers, Request/Response Models |
| **Service Layer** | 비즈니스 로직, 트랜잭션 조정 | Services, Saga Coordinator |
| **Repository Layer** | 데이터 접근 추상화 | Repositories |
| **Infrastructure Layer** | 외부 시스템 연결 | DB Clients, Message Queue |

---

## 4. Component Design

### 4.1 API Layer

#### 4.1.1 Router Structure

```
src/api/
├── __init__.py
├── dependencies.py          # 의존성 주입
├── routers/
│   ├── __init__.py
│   ├── documents.py         # POST/GET/PUT/DELETE /documents
│   ├── search.py            # POST /search
│   ├── health.py            # GET /health
│   └── metrics.py           # GET /metrics
└── schemas/
    ├── __init__.py
    ├── documents.py         # Document request/response schemas
    ├── search.py            # Search request/response schemas
    └── common.py            # Common schemas
```

#### 4.1.2 API Endpoints

| Method | Endpoint | Request | Response | Description |
|--------|----------|---------|----------|-------------|
| POST | `/api/v1/documents` | DocumentCreateRequest | DocumentResponse | 문서 저장 |
| GET | `/api/v1/documents/{doc_uuid}` | - | DocumentResponse | 문서 조회 |
| PUT | `/api/v1/documents/{doc_uuid}` | DocumentUpdateRequest | DocumentResponse | 문서 수정 |
| DELETE | `/api/v1/documents/{doc_uuid}` | - | 204 No Content | 문서 삭제 |
| POST | `/api/v1/search` | SearchRequest | SearchResponse | Hybrid Search |
| GET | `/api/v1/health` | - | HealthResponse | Health Check |
| GET | `/api/v1/metrics` | - | Prometheus Format | Metrics |

#### 4.1.3 Request/Response Schemas

```python
# DocumentCreateRequest
class DocumentCreateRequest(BaseModel):
    title: str
    source: Literal["wiki", "agit", "gdocs", "slack"]
    source_url: str
    owner_id: str
    owner_org: str
    security_level: Literal["public", "internal", "confidential"]
    chunks: list[ChunkInput]
    acl_entries: list[AclEntryInput]

class ChunkInput(BaseModel):
    chunk_no: int
    section_path: str
    text: str
    entities: list[EntityInput] = []

# SearchRequest
class SearchRequest(BaseModel):
    query: str
    user_id: str
    user_groups: list[str]
    top_k: int = 10
    search_types: list[Literal["dense", "sparse", "graph"]] = ["dense", "sparse", "graph"]

# SearchResponse
class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
    search_time_ms: float

class SearchResult(BaseModel):
    chunk_uuid: str
    doc_uuid: str
    title: str
    chunk_text: str
    score: float
    search_type: str
    metadata: dict
```

---

### 4.2 Service Layer

#### 4.2.1 Service Structure

```
src/services/
├── __init__.py
├── document_service.py      # 문서 CRUD 비즈니스 로직
├── search_service.py        # Hybrid Search 로직
├── acl_service.py           # 권한 관리 로직
├── sync_service.py          # 변경 동기화 로직
├── embedding_service.py     # BGE-M3 임베딩 생성
└── saga/
    ├── __init__.py
    ├── coordinator.py       # Saga 조정자
    └── steps.py             # Saga 단계 정의
```

#### 4.2.2 Document Service

```python
class DocumentService:
    """문서 저장/조회/수정/삭제 비즈니스 로직"""

    def __init__(
        self,
        postgres_repo: PostgresRepository,
        milvus_repo: MilvusRepository,
        neo4j_repo: Neo4jRepository,
        embedding_service: EmbeddingService,
        saga_coordinator: SagaCoordinator,
        kafka_producer: KafkaProducer,
    ):
        ...

    async def create_document(self, request: DocumentCreateRequest) -> DocumentResponse:
        """
        1. 임베딩 생성 (BGE-M3)
        2. Saga 패턴으로 3개 저장소 저장
        3. Kafka 이벤트 발행
        4. 응답 반환
        """

    async def get_document(self, doc_uuid: str) -> DocumentResponse:
        """PostgreSQL에서 문서 메타데이터 조회"""

    async def update_document(self, doc_uuid: str, request: DocumentUpdateRequest) -> DocumentResponse:
        """
        1. 기존 데이터 조회
        2. 변경 사항 임베딩 생성
        3. Saga 패턴으로 3개 저장소 업데이트
        4. Kafka 이벤트 발행
        """

    async def delete_document(self, doc_uuid: str) -> None:
        """Saga 패턴으로 3개 저장소에서 삭제"""
```

#### 4.2.3 Search Service

```python
class SearchService:
    """Hybrid Search 비즈니스 로직"""

    async def hybrid_search(self, request: SearchRequest) -> SearchResponse:
        """
        1. ACL 필터링 (접근 가능한 doc_uuids 조회)
        2. 병렬 검색 실행
           - Dense Search (Milvus)
           - Sparse Search (Milvus)
           - Graph Search (Neo4j)
        3. 결과 통합 및 반환
        """

    async def _dense_search(self, query_embedding: list[float], doc_uuids: list[str], top_k: int) -> list[SearchResult]:
        """Milvus Dense Vector 코사인 유사도 검색"""

    async def _sparse_search(self, query_sparse: dict, doc_uuids: list[str], top_k: int) -> list[SearchResult]:
        """Milvus Sparse Vector BM25 검색"""

    async def _graph_search(self, query: str, doc_uuids: list[str], top_k: int) -> list[SearchResult]:
        """Neo4j Cypher 기반 관계 탐색"""
```

#### 4.2.4 Saga Coordinator (분산 트랜잭션)

```python
class SagaCoordinator:
    """3개 저장소 분산 트랜잭션 관리 (Saga 패턴)"""

    async def execute_create_saga(self, document: Document, chunks: list[Chunk]) -> SagaResult:
        """
        Forward Steps:
        1. PostgreSQL: 문서/청크 메타데이터 저장
        2. Milvus: 벡터 임베딩 저장
        3. Neo4j: 그래프 노드/엣지 생성

        Compensating Steps (실패 시):
        3. Neo4j: 노드/엣지 삭제
        2. Milvus: 벡터 삭제
        1. PostgreSQL: 문서/청크 삭제
        """

    async def execute_delete_saga(self, doc_uuid: str) -> SagaResult:
        """삭제 Saga (역순)"""
```

**Saga 실행 흐름:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CREATE DOCUMENT SAGA                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐   │
│  │  Start   │────▶│PostgreSQL│────▶│  Milvus  │────▶│  Neo4j   │   │
│  │          │     │  Save    │     │  Save    │     │  Save    │   │
│  └──────────┘     └────┬─────┘     └────┬─────┘     └────┬─────┘   │
│                        │                │                │          │
│                        │ Success        │ Success        │ Success  │
│                        ▼                ▼                ▼          │
│                   ┌─────────────────────────────────────────┐       │
│                   │              COMMIT                      │       │
│                   └─────────────────────────────────────────┘       │
│                                                                      │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─   │
│                         COMPENSATION (Failure)                       │
│                                                                      │
│                   ┌──────────┐     ┌──────────┐                     │
│                   │PostgreSQL│◀────│  Milvus  │◀──── [Failure]      │
│                   │  Delete  │     │  Delete  │                     │
│                   └──────────┘     └──────────┘                     │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 4.3 Repository Layer

#### 4.3.1 Repository Structure

```
src/repositories/
├── __init__.py
├── base.py                  # Abstract Repository
├── postgres/
│   ├── __init__.py
│   ├── repository.py        # PostgreSQL Repository
│   ├── models.py            # SQLAlchemy Models
│   └── queries.py           # SQL Queries
├── milvus/
│   ├── __init__.py
│   ├── repository.py        # Milvus Repository
│   └── schemas.py           # Collection Schemas
├── neo4j/
│   ├── __init__.py
│   ├── repository.py        # Neo4j Repository
│   └── queries.py           # Cypher Queries
└── kafka/
    ├── __init__.py
    ├── producer.py          # Kafka Producer
    └── consumer.py          # Kafka Consumer
```

#### 4.3.2 PostgreSQL Repository

```python
class PostgresRepository:
    """PostgreSQL 데이터 접근"""

    # Document CRUD
    async def create_document(self, doc: Document) -> Document
    async def get_document(self, doc_uuid: str) -> Document | None
    async def update_document(self, doc_uuid: str, updates: dict) -> Document
    async def delete_document(self, doc_uuid: str) -> None

    # Chunk CRUD
    async def create_chunks(self, chunks: list[Chunk]) -> list[Chunk]
    async def get_chunks_by_doc(self, doc_uuid: str) -> list[Chunk]
    async def delete_chunks_by_doc(self, doc_uuid: str) -> None

    # ACL
    async def get_accessible_doc_uuids(self, user_id: str, groups: list[str]) -> list[str]
    async def create_acl_entries(self, entries: list[AclEntry]) -> None

    # Audit
    async def create_audit_log(self, log: AuditLog) -> None
```

#### 4.3.3 Milvus Repository

```python
class MilvusRepository:
    """Milvus 벡터 데이터 접근"""

    # Vector CRUD
    async def insert_vectors(self, chunks: list[MilvusChunk]) -> list[str]
    async def delete_vectors(self, chunk_uuids: list[str]) -> None

    # Search
    async def dense_search(
        self,
        query_vector: list[float],
        filter_expr: str,
        top_k: int
    ) -> list[SearchHit]

    async def sparse_search(
        self,
        query_sparse: dict[str, float],
        filter_expr: str,
        top_k: int
    ) -> list[SearchHit]

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: dict[str, float],
        filter_expr: str,
        top_k: int,
        dense_weight: float = 0.5
    ) -> list[SearchHit]
```

#### 4.3.4 Neo4j Repository

```python
class Neo4jRepository:
    """Neo4j 그래프 데이터 접근"""

    # Node CRUD
    async def create_document_node(self, doc: DocumentNode) -> str
    async def create_chunk_nodes(self, chunks: list[ChunkNode]) -> list[str]
    async def delete_document_graph(self, doc_uuid: str) -> None

    # Relationship CRUD
    async def create_contains_edges(self, doc_uuid: str, chunk_uuids: list[str]) -> None
    async def create_mentions_edges(self, chunk_uuid: str, entities: list[Entity]) -> None

    # Search
    async def graph_search(
        self,
        query: str,
        doc_uuids: list[str],
        top_k: int
    ) -> list[GraphSearchResult]

    # Cypher Query Example
    """
    MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
    WHERE d.doc_uuid IN $doc_uuids
    AND c.text_preview CONTAINS $keyword
    RETURN c.chunk_uuid, c.text_preview, d.title
    LIMIT $top_k
    """
```

---

### 4.4 Infrastructure Layer

#### 4.4.1 Database Clients

```
src/infrastructure/
├── __init__.py
├── database/
│   ├── __init__.py
│   ├── postgres.py          # asyncpg connection pool
│   ├── milvus.py            # pymilvus client
│   └── neo4j.py             # neo4j-driver async
├── messaging/
│   ├── __init__.py
│   └── kafka.py             # aiokafka producer/consumer
└── embedding/
    ├── __init__.py
    └── bge_m3.py            # BGE-M3 model wrapper
```

#### 4.4.2 Connection Management

```python
# PostgreSQL Connection Pool
class PostgresClient:
    def __init__(self, dsn: str, pool_size: int = 20):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=5,
            max_size=self.pool_size
        )

    async def disconnect(self):
        await self.pool.close()

# Milvus Client
class MilvusClient:
    def __init__(self, host: str, port: int):
        self.connections = MilvusConnections()

    def connect(self):
        self.connections.connect(alias="default", host=self.host, port=self.port)

# Neo4j Client
class Neo4jClient:
    def __init__(self, uri: str, auth: tuple):
        self.driver = AsyncGraphDatabase.driver(uri, auth=auth)

    async def close(self):
        await self.driver.close()
```

---

## 5. Data Flow

### 5.1 Document Create Flow

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────────┐
│  Client │────▶│   API   │────▶│  Document   │────▶│   Embedding  │
│         │     │  Router │     │   Service   │     │   Service    │
└─────────┘     └─────────┘     └──────┬──────┘     └──────────────┘
                                       │
                                       │ BGE-M3 embeddings
                                       ▼
                                ┌──────────────┐
                                │     Saga     │
                                │ Coordinator  │
                                └──────┬───────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
       ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
       │  Postgres   │          │   Milvus    │          │    Neo4j    │
       │  Repository │          │  Repository │          │  Repository │
       └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
              │                        │                        │
              ▼                        ▼                        ▼
       ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
       │ PostgreSQL  │          │   Milvus    │          │    Neo4j    │
       └─────────────┘          └─────────────┘          └─────────────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │    Kafka    │
                                │  (Event)    │
                                └─────────────┘
```

### 5.2 Hybrid Search Flow

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  Client │────▶│   API   │────▶│   Search    │────▶│     ACL     │
│         │     │  Router │     │   Service   │     │   Service   │
└─────────┘     └─────────┘     └──────┬──────┘     └──────┬──────┘
                                       │                    │
                                       │◀───────────────────┘
                                       │   accessible_doc_uuids
                                       │
                                       ▼
                                ┌──────────────┐
                                │   Parallel   │
                                │   Search     │
                                └──────┬───────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
       ┌─────────────┐          ┌─────────────┐          ┌─────────────┐
       │   Dense     │          │   Sparse    │          │    Graph    │
       │   Search    │          │   Search    │          │   Search    │
       │  (Milvus)   │          │  (Milvus)   │          │   (Neo4j)   │
       └──────┬──────┘          └──────┬──────┘          └──────┬──────┘
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │    Merge     │
                                │   Results    │
                                └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │   Response   │
                                └──────────────┘
```

### 5.3 Sync Event Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Kafka     │────▶│    Sync     │────▶│  Repository │
│  Consumer   │     │   Service   │     │   Layer     │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       │ document.updated
       │ document.deleted
       ▼
┌─────────────────────────────────────────────────────┐
│              Sync Service Logic                      │
├─────────────────────────────────────────────────────┤
│  1. Parse event payload                             │
│  2. Determine affected stores                       │
│  3. Execute updates in each store                   │
│  4. Verify consistency                              │
│  5. Emit sync.completed event                       │
└─────────────────────────────────────────────────────┘
```

---

## 6. Database Design

### 6.1 PostgreSQL Schema

```sql
-- Documents (정본 관리)
CREATE TABLE documents (
    doc_uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    source          VARCHAR(50) NOT NULL,
    source_url      VARCHAR(2000) NOT NULL,
    owner_id        VARCHAR(100) NOT NULL,
    owner_org       VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft',
    security_level  VARCHAR(20) NOT NULL DEFAULT 'internal',
    current_version_id UUID,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_documents_owner ON documents(owner_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_security ON documents(security_level);

-- Document Versions (버전 관리)
CREATE TABLE document_versions (
    version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    effective_from  TIMESTAMP WITH TIME ZONE,
    approved_by     VARCHAR(100),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, version_no)
);

CREATE INDEX idx_versions_doc ON document_versions(doc_uuid);

-- Document Chunks (ID 매핑)
CREATE TABLE document_chunks (
    chunk_uuid      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    chunk_no        INTEGER NOT NULL,
    section_path    VARCHAR(100),
    milvus_id       VARCHAR(100),
    neo4j_node_id   VARCHAR(100),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_chunks_doc ON document_chunks(doc_uuid);
CREATE INDEX idx_chunks_milvus ON document_chunks(milvus_id);

-- ACL Entries (권한 관리)
CREATE TABLE acl_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    principal_type  VARCHAR(20) NOT NULL,  -- 'user', 'group', 'org'
    principal_id    VARCHAR(100) NOT NULL,
    permission      VARCHAR(20) NOT NULL,  -- 'read', 'write', 'admin'
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, principal_type, principal_id)
);

CREATE INDEX idx_acl_principal ON acl_entries(principal_type, principal_id);

-- Audit Logs (감사 로그)
CREATE TABLE audit_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(100) NOT NULL,
    action          VARCHAR(20) NOT NULL,
    doc_uuid        UUID,
    query_text      TEXT,
    retrieved_docs  UUID[],
    metadata        JSONB,
    timestamp       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_timestamp ON audit_logs(timestamp);
```

### 6.2 Milvus Collection Schema

```python
from pymilvus import CollectionSchema, FieldSchema, DataType

# Collection: knowledge_chunks
fields = [
    FieldSchema(name="chunk_uuid", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
    FieldSchema(name="doc_uuid", dtype=DataType.VARCHAR, max_length=36),
    FieldSchema(name="dense_embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema(name="sparse_embedding", dtype=DataType.SPARSE_FLOAT_VECTOR),
    FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=8000),
    FieldSchema(name="security_level", dtype=DataType.VARCHAR, max_length=20),
    FieldSchema(name="allowed_groups", dtype=DataType.ARRAY, element_type=DataType.VARCHAR, max_length=100, max_capacity=50),
    FieldSchema(name="created_at", dtype=DataType.INT64),
]

schema = CollectionSchema(fields=fields, description="Knowledge Store Chunks")

# Indexes
index_params = {
    "dense_embedding": {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {"M": 16, "efConstruction": 256}
    },
    "sparse_embedding": {
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "IP"
    }
}
```

### 6.3 Neo4j Graph Schema

```cypher
// Constraints (Unique)
CREATE CONSTRAINT doc_uuid_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_uuid IS UNIQUE;

CREATE CONSTRAINT chunk_uuid_unique IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_uuid IS UNIQUE;

CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.emp_id IS UNIQUE;

CREATE CONSTRAINT org_id_unique IF NOT EXISTS
FOR (o:Organization) REQUIRE o.org_id IS UNIQUE;

// Indexes (Search Performance)
CREATE INDEX doc_title_idx IF NOT EXISTS
FOR (d:Document) ON (d.title);

CREATE INDEX chunk_text_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.text_preview);

CREATE INDEX person_name_idx IF NOT EXISTS
FOR (p:Person) ON (p.name);

// Node Labels
// :Document {doc_uuid, title, source, security_level, created_at}
// :Chunk {chunk_uuid, sequence, text_preview, section_path}
// :Person {emp_id, name, department, role, email}
// :Organization {org_id, name, parent_org_id}
// :Project {project_id, name, status, start_date}
// :Policy {policy_id, name, effective_from}

// Relationship Types
// (Person)-[:WROTE {created_at}]->(Document)
// (Document)-[:CONTAINS {sequence}]->(Chunk)
// (Chunk)-[:MENTIONS {confidence}]->(Entity)
// (Person)-[:MANAGES {role}]->(Project)
// (Person)-[:BELONGS_TO {joined_at}]->(Organization)
// (Organization)-[:HAS_POLICY]->(Policy)
```

---

## 7. Project Structure

```
knowledge-store/
├── src/
│   ├── __init__.py
│   ├── main.py                      # FastAPI 애플리케이션 진입점
│   ├── config.py                    # 설정 관리 (Pydantic Settings)
│   │
│   ├── api/                         # API Layer
│   │   ├── __init__.py
│   │   ├── dependencies.py          # 의존성 주입
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── documents.py
│   │   │   ├── search.py
│   │   │   ├── health.py
│   │   │   └── metrics.py
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── documents.py
│   │       ├── search.py
│   │       └── common.py
│   │
│   ├── services/                    # Service Layer
│   │   ├── __init__.py
│   │   ├── document_service.py
│   │   ├── search_service.py
│   │   ├── acl_service.py
│   │   ├── sync_service.py
│   │   ├── embedding_service.py
│   │   └── saga/
│   │       ├── __init__.py
│   │       ├── coordinator.py
│   │       └── steps.py
│   │
│   ├── repositories/                # Repository Layer
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── postgres/
│   │   │   ├── __init__.py
│   │   │   ├── repository.py
│   │   │   ├── models.py
│   │   │   └── queries.py
│   │   ├── milvus/
│   │   │   ├── __init__.py
│   │   │   ├── repository.py
│   │   │   └── schemas.py
│   │   ├── neo4j/
│   │   │   ├── __init__.py
│   │   │   ├── repository.py
│   │   │   └── queries.py
│   │   └── kafka/
│   │       ├── __init__.py
│   │       ├── producer.py
│   │       └── consumer.py
│   │
│   ├── infrastructure/              # Infrastructure Layer
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── postgres.py
│   │   │   ├── milvus.py
│   │   │   └── neo4j.py
│   │   ├── messaging/
│   │   │   ├── __init__.py
│   │   │   └── kafka.py
│   │   └── embedding/
│   │       ├── __init__.py
│   │       └── bge_m3.py
│   │
│   └── domain/                      # Domain Models
│       ├── __init__.py
│       ├── document.py
│       ├── chunk.py
│       ├── search.py
│       └── events.py
│
├── tests/                           # Tests
│   ├── __init__.py
│   ├── conftest.py                  # Pytest fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_services/
│   │   └── test_repositories/
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_document_flow.py
│   │   ├── test_search_flow.py
│   │   └── test_sync_flow.py
│   └── e2e/
│       ├── __init__.py
│       └── test_full_cycle.py
│
├── scripts/                         # Utility Scripts
│   ├── init_postgres.py
│   ├── init_milvus.py
│   ├── init_neo4j.py
│   └── seed_data.py
│
├── docker/                          # Docker Configuration
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── Dockerfile
│
├── docs/                            # Documentation
│   ├── prd/
│   ├── tech-stack/
│   └── architecture/
│
├── pyproject.toml                   # Project Configuration
├── .env.example                     # Environment Variables
├── .gitignore
└── README.md
```

---

## 8. Deployment Architecture

### 8.1 Local Development (Docker Compose)

```
┌────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Network                       │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │   FastAPI   │  │ PostgreSQL  │  │   Milvus    │  │   Neo4j   │ │
│  │   :8000     │  │   :5432     │  │   :19530    │  │   :7687   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │    Kafka    │  │    etcd     │  │    MinIO    │                │
│  │   :9092     │  │   :2379     │  │   :9000     │                │
│  └─────────────┘  └─────────────┘  └─────────────┘                │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### 8.2 Environment Variables

```bash
# .env.example

# Application
APP_NAME=knowledge-store-layer
APP_ENV=development
DEBUG=true

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledge_store
POSTGRES_USER=ks_user
POSTGRES_PASSWORD=ks_password
POSTGRES_POOL_SIZE=20

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=knowledge_chunks

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP=knowledge-store

# Embedding
BGE_M3_MODEL=BAAI/bge-m3
BGE_M3_USE_FP16=true

# Metrics
PROMETHEUS_PORT=9090
```

---

## 9. Cross-Cutting Concerns

### 9.1 Error Handling

```python
# Custom Exceptions
class KnowledgeStoreError(Exception):
    """Base exception"""

class DocumentNotFoundError(KnowledgeStoreError):
    """Document not found"""

class AccessDeniedError(KnowledgeStoreError):
    """Access denied"""

class SagaExecutionError(KnowledgeStoreError):
    """Saga execution failed"""

# Error Handler
@app.exception_handler(KnowledgeStoreError)
async def knowledge_store_error_handler(request: Request, exc: KnowledgeStoreError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": str(exc)}
    )
```

### 9.2 Logging

```python
import structlog

# Structured Logging Configuration
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Usage
logger = structlog.get_logger()
logger.info("document_created", doc_uuid=doc_uuid, chunks_count=len(chunks))
```

### 9.3 Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Metrics
SEARCH_REQUESTS = Counter(
    'search_requests_total',
    'Total search requests',
    ['search_type']
)

SEARCH_LATENCY = Histogram(
    'search_latency_seconds',
    'Search latency',
    ['search_type'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

DOCUMENT_COUNT = Gauge(
    'documents_total',
    'Total documents in store'
)

# Usage
@SEARCH_LATENCY.labels(search_type='hybrid').time()
async def hybrid_search(request: SearchRequest):
    SEARCH_REQUESTS.labels(search_type='hybrid').inc()
    ...
```

### 9.4 Health Check

```python
@router.get("/health")
async def health_check(
    postgres: PostgresClient = Depends(get_postgres),
    milvus: MilvusClient = Depends(get_milvus),
    neo4j: Neo4jClient = Depends(get_neo4j),
    kafka: KafkaClient = Depends(get_kafka),
):
    checks = {
        "postgres": await postgres.ping(),
        "milvus": await milvus.ping(),
        "neo4j": await neo4j.ping(),
        "kafka": await kafka.ping(),
    }

    status = "healthy" if all(checks.values()) else "unhealthy"
    return {"status": status, "checks": checks}
```

---

## 10. Security Considerations

### 10.1 ACL Implementation

```python
class AclService:
    """ACL 기반 접근 제어"""

    async def get_accessible_documents(
        self,
        user_id: str,
        user_groups: list[str]
    ) -> list[str]:
        """
        사용자가 접근 가능한 문서 ID 목록 반환

        조건:
        1. principal_type='user' AND principal_id=user_id
        2. principal_type='group' AND principal_id IN user_groups
        3. principal_type='org' AND principal_id='ALL'
        """

    async def check_access(
        self,
        user_id: str,
        user_groups: list[str],
        doc_uuid: str,
        required_permission: str
    ) -> bool:
        """특정 문서에 대한 권한 확인"""
```

### 10.2 Audit Logging

```python
class AuditLogger:
    """감사 로그 기록"""

    async def log_search(
        self,
        user_id: str,
        query: str,
        retrieved_docs: list[str]
    ):
        await self.postgres_repo.create_audit_log(
            AuditLog(
                user_id=user_id,
                action="search",
                query_text=query,
                retrieved_docs=retrieved_docs
            )
        )

    async def log_document_access(
        self,
        user_id: str,
        doc_uuid: str,
        action: str
    ):
        await self.postgres_repo.create_audit_log(
            AuditLog(
                user_id=user_id,
                action=action,
                doc_uuid=doc_uuid
            )
        )
```

---

## 11. Performance Optimization

### 11.1 Connection Pooling

| Database | Pool Size | Min | Max Overflow |
|----------|-----------|-----|--------------|
| PostgreSQL | 20 | 5 | 10 |
| Milvus | 10 | 2 | 5 |
| Neo4j | 50 | 10 | 20 |

### 11.2 Parallel Search

```python
async def hybrid_search(self, request: SearchRequest) -> SearchResponse:
    start_time = time.time()

    # 1. ACL 필터링 (필수)
    accessible_docs = await self.acl_service.get_accessible_documents(
        request.user_id, request.user_groups
    )

    if not accessible_docs:
        return SearchResponse(results=[], total=0, search_time_ms=0)

    # 2. 쿼리 임베딩 생성
    query_embedding = await self.embedding_service.encode(request.query)

    # 3. 병렬 검색 (asyncio.gather)
    tasks = []
    if "dense" in request.search_types:
        tasks.append(self._dense_search(query_embedding.dense, accessible_docs, request.top_k))
    if "sparse" in request.search_types:
        tasks.append(self._sparse_search(query_embedding.sparse, accessible_docs, request.top_k))
    if "graph" in request.search_types:
        tasks.append(self._graph_search(request.query, accessible_docs, request.top_k))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 4. 결과 병합
    merged = self._merge_results(results, request.top_k)

    return SearchResponse(
        results=merged,
        total=len(merged),
        search_time_ms=(time.time() - start_time) * 1000
    )
```

### 11.3 Caching Strategy (Future)

| Cache Target | TTL | Invalidation |
|--------------|-----|--------------|
| ACL Results | 5 min | Document update |
| Search Results | 1 min | Document change |
| Embeddings | 24 hours | Model update |

---

## 12. Testing Strategy

### 12.1 Test Pyramid

```
                    ┌─────────┐
                    │   E2E   │  ← 5% (Critical paths)
                    │  Tests  │
                 ┌──┴─────────┴──┐
                 │  Integration  │  ← 25% (Service + Repository)
                 │     Tests     │
              ┌──┴───────────────┴──┐
              │     Unit Tests       │  ← 70% (Services, Utils)
              └──────────────────────┘
```

### 12.2 Test Configuration

```python
# conftest.py
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.kafka import KafkaContainer

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:15-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def kafka_container():
    with KafkaContainer() as kafka:
        yield kafka

@pytest.fixture
async def test_db(postgres_container):
    # Create test database and return connection
    ...
```

---

## 13. Appendix

### 13.1 PRD Requirement Mapping

| PRD Requirement | Architecture Component | Status |
|-----------------|----------------------|--------|
| FR-1: PostgreSQL Schema | `repositories/postgres/models.py` | Designed |
| FR-2: Milvus Collection | `repositories/milvus/schemas.py` | Designed |
| FR-3: Neo4j Ontology | `repositories/neo4j/queries.py` | Designed |
| FR-4: ID Mapping | `repositories/postgres/repository.py` | Designed |
| FR-5: Document Storage API | `services/document_service.py` + Saga | Designed |
| FR-6: Hybrid Search API | `services/search_service.py` | Designed |
| FR-7: ACL Filtering | `services/acl_service.py` | Designed |
| FR-8: Change Sync | `services/sync_service.py` + Kafka | Designed |

### 13.2 API Summary

| Method | Endpoint | Handler |
|--------|----------|---------|
| POST | `/api/v1/documents` | `documents.create_document` |
| GET | `/api/v1/documents/{doc_uuid}` | `documents.get_document` |
| PUT | `/api/v1/documents/{doc_uuid}` | `documents.update_document` |
| DELETE | `/api/v1/documents/{doc_uuid}` | `documents.delete_document` |
| POST | `/api/v1/search` | `search.hybrid_search` |
| GET | `/api/v1/health` | `health.health_check` |
| GET | `/api/v1/metrics` | `metrics.prometheus_metrics` |

---

## 14. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial architecture design |
