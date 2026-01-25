# Task Breakdown: Knowledge Store Layer

---

## Meta
- **PRD Reference**: [knowledge-store-layer-prd.md](../prd/knowledge-store-layer-prd.md)
- **Architecture Reference**: [architecture.md](../architecture/architecture.md)
- **Tech Stack Reference**: [tech-stack.md](../tech-stack/tech-stack.md)
- **Created**: 2026-01-25
- **Status**: Ready for Implementation

---

## Overview

| Phase | Epic | Tasks | Estimated Hours |
|-------|------|-------|-----------------|
| Phase 1 | 인프라 및 스키마 구축 | 8 | 42h |
| Phase 2 | 핵심 서비스 구현 | 10 | 56h |
| Phase 3 | 검색 기능 구현 | 6 | 32h |
| Phase 4 | 동기화 및 운영 기능 | 6 | 30h |
| **Total** | **4 Epics** | **30 Tasks** | **160h** |

---

# Phase 1: 인프라 및 스키마 구축

## Epic 1.1: 프로젝트 초기 설정

### Task 1.1.1: 프로젝트 구조 생성
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: None

**Description**:
Architecture 문서의 Project Structure에 따라 Python 프로젝트 기본 구조를 생성합니다.

**Acceptance Criteria**:
- [ ] `knowledge-store/` 폴더 구조 생성 (src/, tests/, scripts/, docker/)
- [ ] `pyproject.toml` 생성 (Tech Stack 문서의 dependencies 반영)
- [ ] `.env.example` 생성 (환경 변수 템플릿)
- [ ] `.gitignore` 생성
- [ ] `README.md` 기본 구조 작성
- [ ] `ruff`, `mypy` 설정 파일 생성
- [ ] `pytest` 설정 (`conftest.py`)

**Technical Details**:
```
knowledge-store/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   ├── services/
│   ├── repositories/
│   ├── infrastructure/
│   └── domain/
├── tests/
├── scripts/
├── docker/
├── docs/
├── pyproject.toml
├── .env.example
└── .gitignore
```

**Tests**:
- `python -m pytest` 실행 가능
- `ruff check src/` 통과
- `mypy src/` 통과

---

### Task 1.1.2: 설정 관리 구현 (Pydantic Settings)
- **Estimate**: 2h
- **Priority**: P0
- **Dependencies**: Task 1.1.1

**Description**:
환경 변수 기반 설정 관리 클래스를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/config.py`에 Settings 클래스 구현
- [ ] PostgreSQL, Milvus, Neo4j, Kafka 연결 설정 포함
- [ ] `.env` 파일에서 설정 로드
- [ ] 설정 검증 (필수 값 누락 시 에러)

**Technical Details**:
```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "knowledge_store"
    postgres_user: str
    postgres_password: str

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    class Config:
        env_file = ".env"
```

**Tests**:
- `test_settings_load()`: 환경 변수에서 설정 로드 확인
- `test_settings_validation()`: 필수 값 누락 시 ValidationError

---

## Epic 1.2: Docker 인프라 구축

### Task 1.2.1: 기존 Docker 인프라 확인
- **Estimate**: 2h
- **Priority**: P0
- **Dependencies**: None

**Description**:
현재 설치된 Docker 컨테이너 현황을 확인하고, 필요 버전과 비교합니다.

**Acceptance Criteria**:
- [ ] `docker ps -a` 실행하여 현재 컨테이너 목록 확인
- [ ] PostgreSQL, Milvus, Neo4j, Kafka 설치 여부 확인
- [ ] 설치된 버전과 필요 버전 비교
- [ ] Gap 분석 결과 문서화

**Technical Details**:
| Component | Required Version | Check Command |
|-----------|-----------------|---------------|
| PostgreSQL | 15+ | `docker exec postgres psql -V` |
| Milvus | 2.5+ | API `/v1/version` |
| Neo4j | 5.x | `docker exec neo4j neo4j --version` |
| Kafka | 3.x | `kafka-topics.sh --version` |

**Output**:
- `docs/infrastructure-status.md` 파일 생성

---

### Task 1.2.2: Docker Compose 설정
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.2.1

**Description**:
Tech Stack 문서의 Docker Compose 설정을 기반으로 `docker-compose.yml`을 생성합니다.

**Acceptance Criteria**:
- [ ] `docker/docker-compose.yml` 생성
- [ ] PostgreSQL 15-alpine 설정
- [ ] Milvus 2.5 Standalone 설정 (etcd, minio 포함)
- [ ] Neo4j 5.x Community 설정
- [ ] Kafka 3.x KRaft 모드 설정
- [ ] 모든 컨테이너 healthcheck 설정
- [ ] `docker compose up -d` 실행 성공

**Technical Details**:
- Tech Stack 문서 Section 4.2 참조
- Volume 영속성 설정
- Network 설정

**Tests**:
- `docker compose up -d` 성공
- `docker compose ps` 모든 서비스 healthy
- 각 서비스 포트 접근 가능

---

### Task 1.2.3: 인프라 연결 테스트 스크립트
- **Estimate**: 2h
- **Priority**: P0
- **Dependencies**: Task 1.2.2

**Description**:
각 인프라 컴포넌트에 연결 가능한지 확인하는 스크립트를 작성합니다.

**Acceptance Criteria**:
- [ ] `scripts/check_infrastructure.py` 생성
- [ ] PostgreSQL 연결 테스트
- [ ] Milvus 연결 테스트
- [ ] Neo4j 연결 테스트
- [ ] Kafka 연결 테스트
- [ ] 모든 연결 성공 시 "All connections OK" 출력

**Technical Details**:
```python
# scripts/check_infrastructure.py
import asyncio
import asyncpg
from pymilvus import connections
from neo4j import AsyncGraphDatabase
from aiokafka import AIOKafkaProducer

async def check_all():
    # PostgreSQL
    conn = await asyncpg.connect(...)
    await conn.close()
    print("✅ PostgreSQL OK")

    # Milvus
    connections.connect(...)
    print("✅ Milvus OK")

    # Neo4j
    driver = AsyncGraphDatabase.driver(...)
    await driver.verify_connectivity()
    print("✅ Neo4j OK")

    # Kafka
    producer = AIOKafkaProducer(...)
    await producer.start()
    await producer.stop()
    print("✅ Kafka OK")
```

**Tests**:
- `python scripts/check_infrastructure.py` 성공

---

## Epic 1.3: 데이터베이스 스키마 구축

### Task 1.3.1: PostgreSQL 스키마 마이그레이션
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.2.2

**Description**:
Architecture 문서의 PostgreSQL 스키마를 생성합니다.

**Acceptance Criteria**:
- [ ] `scripts/init_postgres.py` 생성
- [ ] `documents` 테이블 생성
- [ ] `document_versions` 테이블 생성
- [ ] `document_chunks` 테이블 생성
- [ ] `acl_entries` 테이블 생성
- [ ] `audit_logs` 테이블 생성
- [ ] 모든 인덱스 생성
- [ ] FK 제약조건 설정

**Technical Details**:
- Architecture 문서 Section 6.1 참조
- SQLAlchemy Models는 Phase 2에서 구현

**SQL Script**:
```sql
-- documents
CREATE TABLE documents (
    doc_uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    ...
);

-- indexes
CREATE INDEX idx_documents_owner ON documents(owner_id);
...
```

**Tests**:
- `\dt` 명령으로 5개 테이블 확인
- `\di` 명령으로 인덱스 확인

---

### Task 1.3.2: Milvus Collection 생성
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.2.2

**Description**:
Architecture 문서의 Milvus Collection 스키마를 생성합니다.

**Acceptance Criteria**:
- [ ] `scripts/init_milvus.py` 생성
- [ ] `knowledge_chunks` Collection 생성
- [ ] 필드 정의 (chunk_uuid, doc_uuid, dense_embedding, sparse_embedding, ...)
- [ ] HNSW 인덱스 생성 (dense_embedding)
- [ ] SPARSE_INVERTED_INDEX 생성 (sparse_embedding)
- [ ] Collection 로드 확인

**Technical Details**:
- Architecture 문서 Section 6.2 참조
- Dense: FLOAT_VECTOR[1024]
- Sparse: SPARSE_FLOAT_VECTOR

```python
from pymilvus import Collection, FieldSchema, CollectionSchema, DataType

fields = [
    FieldSchema(name="chunk_uuid", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
    FieldSchema(name="doc_uuid", dtype=DataType.VARCHAR, max_length=36),
    FieldSchema(name="dense_embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema(name="sparse_embedding", dtype=DataType.SPARSE_FLOAT_VECTOR),
    ...
]
```

**Tests**:
- Collection 존재 확인
- 인덱스 상태 확인
- 간단한 insert/search 테스트

---

### Task 1.3.3: Neo4j 온톨로지 구축
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.2.2

**Description**:
Architecture 문서의 Neo4j 스키마(제약조건, 인덱스)를 생성합니다.

**Acceptance Criteria**:
- [ ] `scripts/init_neo4j.py` 생성
- [ ] Unique Constraints 생성 (doc_uuid, chunk_uuid, emp_id, org_id)
- [ ] 검색용 인덱스 생성 (title, text_preview, name)
- [ ] 제약조건/인덱스 생성 확인

**Technical Details**:
- Architecture 문서 Section 6.3 참조

```cypher
CREATE CONSTRAINT doc_uuid_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_uuid IS UNIQUE;

CREATE INDEX doc_title_idx IF NOT EXISTS
FOR (d:Document) ON (d.title);
```

**Tests**:
- `SHOW CONSTRAINTS` 확인
- `SHOW INDEXES` 확인

---

### Task 1.3.4: 스키마 초기화 통합 스크립트
- **Estimate**: 2h
- **Priority**: P1
- **Dependencies**: Task 1.3.1, 1.3.2, 1.3.3

**Description**:
모든 데이터베이스 스키마를 한 번에 초기화하는 통합 스크립트를 작성합니다.

**Acceptance Criteria**:
- [ ] `scripts/init_all.py` 생성
- [ ] PostgreSQL, Milvus, Neo4j 순서대로 초기화
- [ ] 이미 존재하는 경우 스킵 또는 재생성 옵션
- [ ] 초기화 결과 출력

**Technical Details**:
```bash
python scripts/init_all.py --reset  # 전체 재생성
python scripts/init_all.py          # 없는 것만 생성
```

**Tests**:
- `--reset` 옵션으로 전체 재생성 성공
- 중복 실행 시 에러 없음

---

# Phase 2: 핵심 서비스 구현

## Epic 2.1: Infrastructure Layer (DB Clients)

### Task 2.1.1: PostgreSQL Client 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.3.1

**Description**:
asyncpg 기반 PostgreSQL 연결 및 Connection Pool을 관리하는 클라이언트를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/infrastructure/database/postgres.py` 생성
- [ ] Connection Pool 생성/종료 메서드
- [ ] 트랜잭션 컨텍스트 매니저
- [ ] 연결 상태 확인 (ping)

**Technical Details**:
```python
class PostgresClient:
    def __init__(self, dsn: str, pool_size: int = 20):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(...)

    async def disconnect(self) -> None:
        await self.pool.close()

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn
```

**Tests**:
- `test_connect_disconnect()`
- `test_transaction_commit()`
- `test_transaction_rollback()`

---

### Task 2.1.2: Milvus Client 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.3.2

**Description**:
pymilvus 기반 Milvus 연결 및 기본 연산을 관리하는 클라이언트를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/infrastructure/database/milvus.py` 생성
- [ ] 연결/종료 메서드
- [ ] Collection 로드/릴리스
- [ ] Insert, Delete, Search 기본 메서드
- [ ] 연결 상태 확인 (ping)

**Technical Details**:
```python
class MilvusClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.collection: Collection | None = None

    def connect(self) -> None:
        connections.connect(alias="default", host=self.host, port=self.port)
        self.collection = Collection("knowledge_chunks")
        self.collection.load()
```

**Tests**:
- `test_connect_disconnect()`
- `test_insert_delete()`
- `test_search()`

---

### Task 2.1.3: Neo4j Client 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.3.3

**Description**:
neo4j-driver 기반 Neo4j 연결 및 기본 연산을 관리하는 클라이언트를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/infrastructure/database/neo4j.py` 생성
- [ ] 비동기 드라이버 생성/종료
- [ ] 세션 컨텍스트 매니저
- [ ] Cypher 쿼리 실행 메서드
- [ ] 연결 상태 확인 (ping)

**Technical Details**:
```python
class Neo4jClient:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        await self.driver.close()

    async def execute_query(self, query: str, parameters: dict = None):
        async with self.driver.session() as session:
            result = await session.run(query, parameters)
            return [record async for record in result]
```

**Tests**:
- `test_connect_disconnect()`
- `test_create_node()`
- `test_create_relationship()`
- `test_query()`

---

### Task 2.1.4: Kafka Client 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.2.2

**Description**:
aiokafka 기반 Kafka Producer/Consumer를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/infrastructure/messaging/kafka.py` 생성
- [ ] Producer 클래스 (메시지 발행)
- [ ] Consumer 클래스 (메시지 구독)
- [ ] JSON 직렬화/역직렬화
- [ ] 연결 상태 확인

**Technical Details**:
```python
class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(...)

    async def send(self, topic: str, value: dict, key: str = None):
        await self.producer.send_and_wait(topic, json.dumps(value).encode())

class KafkaConsumer:
    def __init__(self, bootstrap_servers: str, group_id: str, topics: list[str]):
        self.consumer = AIOKafkaConsumer(*topics, ...)

    async def consume(self):
        async for msg in self.consumer:
            yield json.loads(msg.value)
```

**Tests**:
- `test_producer_send()`
- `test_consumer_receive()`

---

## Epic 2.2: Repository Layer

### Task 2.2.1: PostgreSQL Repository 구현
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 2.1.1

**Description**:
PostgreSQL 데이터 접근 레이어를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/repositories/postgres/repository.py` 생성
- [ ] Document CRUD 메서드
- [ ] Chunk CRUD 메서드
- [ ] ACL 조회/생성 메서드
- [ ] Audit Log 생성 메서드
- [ ] SQLAlchemy Models (`models.py`)

**Technical Details**:
```python
class PostgresRepository:
    async def create_document(self, doc: Document) -> Document
    async def get_document(self, doc_uuid: str) -> Document | None
    async def update_document(self, doc_uuid: str, updates: dict) -> Document
    async def delete_document(self, doc_uuid: str) -> None
    async def create_chunks(self, chunks: list[Chunk]) -> list[Chunk]
    async def get_accessible_doc_uuids(self, user_id: str, groups: list[str]) -> list[str]
    async def create_audit_log(self, log: AuditLog) -> None
```

**Tests**:
- Document CRUD 테스트
- Chunk CRUD 테스트
- ACL 조회 테스트
- 트랜잭션 롤백 테스트

---

### Task 2.2.2: Milvus Repository 구현
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 2.1.2

**Description**:
Milvus 벡터 데이터 접근 레이어를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/repositories/milvus/repository.py` 생성
- [ ] Vector Insert 메서드
- [ ] Vector Delete 메서드
- [ ] Dense Search 메서드
- [ ] Sparse Search 메서드
- [ ] Hybrid Search 메서드

**Technical Details**:
```python
class MilvusRepository:
    async def insert_vectors(self, chunks: list[MilvusChunk]) -> list[str]
    async def delete_vectors(self, chunk_uuids: list[str]) -> None
    async def dense_search(self, query_vector: list[float], filter_expr: str, top_k: int) -> list[SearchHit]
    async def sparse_search(self, query_sparse: dict, filter_expr: str, top_k: int) -> list[SearchHit]
    async def hybrid_search(self, query_dense: list[float], query_sparse: dict, filter_expr: str, top_k: int) -> list[SearchHit]
```

**Tests**:
- Insert/Delete 테스트
- Dense Search 테스트
- Sparse Search 테스트
- Filter 표현식 테스트

---

### Task 2.2.3: Neo4j Repository 구현
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 2.1.3

**Description**:
Neo4j 그래프 데이터 접근 레이어를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/repositories/neo4j/repository.py` 생성
- [ ] Document Node CRUD 메서드
- [ ] Chunk Node CRUD 메서드
- [ ] Relationship 생성 메서드 (CONTAINS, WROTE, MENTIONS)
- [ ] Graph Search 메서드

**Technical Details**:
```python
class Neo4jRepository:
    async def create_document_node(self, doc: DocumentNode) -> str
    async def create_chunk_nodes(self, chunks: list[ChunkNode]) -> list[str]
    async def create_contains_edges(self, doc_uuid: str, chunk_uuids: list[str]) -> None
    async def delete_document_graph(self, doc_uuid: str) -> None
    async def graph_search(self, query: str, doc_uuids: list[str], top_k: int) -> list[GraphSearchResult]
```

**Tests**:
- Node CRUD 테스트
- Relationship 테스트
- Graph Search 테스트

---

## Epic 2.3: Service Layer (Core Services)

### Task 2.3.1: Embedding Service 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 1.1.1

**Description**:
BGE-M3 모델을 사용하여 Dense + Sparse 임베딩을 생성하는 서비스를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/infrastructure/embedding/bge_m3.py` 생성
- [ ] BGE-M3 모델 로드 (lazy loading)
- [ ] Dense + Sparse 임베딩 동시 생성
- [ ] Batch 처리 지원
- [ ] CPU/GPU 자동 감지

**Technical Details**:
```python
from FlagEmbedding import BGEM3FlagModel

class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model: BGEM3FlagModel | None = None

    def _load_model(self):
        if self.model is None:
            self.model = BGEM3FlagModel(self.model_name, use_fp16=True)

    def encode(self, texts: list[str]) -> EmbeddingResult:
        self._load_model()
        output = self.model.encode(texts, return_dense=True, return_sparse=True)
        return EmbeddingResult(
            dense=output['dense_vecs'],
            sparse=output['lexical_weights']
        )
```

**Tests**:
- `test_encode_single()`
- `test_encode_batch()`
- `test_dense_dimension()`: 1024차원 확인
- `test_sparse_format()`: dict 형식 확인

---

### Task 2.3.2: ACL Service 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 2.2.1

**Description**:
ACL 기반 권한 확인 및 필터링 서비스를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/acl_service.py` 생성
- [ ] 접근 가능한 문서 ID 목록 조회
- [ ] 특정 문서 권한 확인
- [ ] 캐싱 고려 (향후 확장)

**Technical Details**:
```python
class AclService:
    def __init__(self, postgres_repo: PostgresRepository):
        self.postgres_repo = postgres_repo

    async def get_accessible_documents(self, user_id: str, user_groups: list[str]) -> list[str]:
        """
        조건:
        1. principal_type='user' AND principal_id=user_id
        2. principal_type='group' AND principal_id IN user_groups
        3. principal_type='org' AND principal_id='ALL'
        """

    async def check_access(self, user_id: str, user_groups: list[str], doc_uuid: str, permission: str) -> bool:
        """특정 문서에 대한 권한 확인"""
```

**Tests**:
- `test_user_access()`
- `test_group_access()`
- `test_org_all_access()`
- `test_no_access()`

---

### Task 2.3.3: Saga Coordinator 구현
- **Estimate**: 8h
- **Priority**: P0
- **Dependencies**: Task 2.2.1, 2.2.2, 2.2.3

**Description**:
3개 저장소에 대한 분산 트랜잭션을 관리하는 Saga Coordinator를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/saga/coordinator.py` 생성
- [ ] `src/services/saga/steps.py` 생성
- [ ] Create Saga (PostgreSQL → Milvus → Neo4j)
- [ ] Delete Saga (Neo4j → Milvus → PostgreSQL)
- [ ] 실패 시 보상 트랜잭션 실행
- [ ] Saga 실행 결과 반환 (성공/실패/보상 내역)

**Technical Details**:
```python
class SagaCoordinator:
    async def execute_create_saga(self, document: Document, chunks: list[Chunk]) -> SagaResult:
        steps = [
            PostgresCreateStep(self.postgres_repo),
            MilvusCreateStep(self.milvus_repo),
            Neo4jCreateStep(self.neo4j_repo),
        ]

        executed = []
        try:
            for step in steps:
                await step.execute(document, chunks)
                executed.append(step)
            return SagaResult(success=True)
        except Exception as e:
            # Compensate in reverse order
            for step in reversed(executed):
                await step.compensate(document.doc_uuid)
            return SagaResult(success=False, error=str(e))
```

**Tests**:
- `test_create_saga_success()`
- `test_create_saga_milvus_fail_compensate()`
- `test_create_saga_neo4j_fail_compensate()`
- `test_delete_saga_success()`

---

# Phase 3: 검색 기능 구현

## Epic 3.1: Search Service

### Task 3.1.1: Dense Search 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 2.2.2, Task 2.3.1

**Description**:
Milvus Dense Vector 코사인 유사도 검색을 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/search_service.py` 생성
- [ ] 쿼리 임베딩 생성 (Dense)
- [ ] Milvus Dense Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

**Technical Details**:
```python
async def _dense_search(
    self,
    query_embedding: list[float],
    accessible_docs: list[str],
    top_k: int
) -> list[SearchResult]:
    filter_expr = f"doc_uuid in {accessible_docs}"
    hits = await self.milvus_repo.dense_search(query_embedding, filter_expr, top_k)
    return [SearchResult(chunk_uuid=h.id, score=h.score, search_type="dense", ...) for h in hits]
```

**Tests**:
- `test_dense_search_basic()`
- `test_dense_search_with_filter()`
- `test_dense_search_empty_result()`

---

### Task 3.1.2: Sparse Search 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 2.2.2, Task 2.3.1

**Description**:
Milvus Sparse Vector (BM25) 키워드 검색을 구현합니다.

**Acceptance Criteria**:
- [ ] 쿼리 임베딩 생성 (Sparse)
- [ ] Milvus Sparse Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

**Technical Details**:
```python
async def _sparse_search(
    self,
    query_sparse: dict[str, float],
    accessible_docs: list[str],
    top_k: int
) -> list[SearchResult]:
    filter_expr = f"doc_uuid in {accessible_docs}"
    hits = await self.milvus_repo.sparse_search(query_sparse, filter_expr, top_k)
    return [SearchResult(chunk_uuid=h.id, score=h.score, search_type="sparse", ...) for h in hits]
```

**Tests**:
- `test_sparse_search_basic()`
- `test_sparse_search_korean()`
- `test_sparse_search_with_filter()`

---

### Task 3.1.3: Graph Search 구현
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 2.2.3

**Description**:
Neo4j Cypher 기반 관계 탐색 검색을 구현합니다.

**Acceptance Criteria**:
- [ ] 키워드 추출 (간단한 토큰화)
- [ ] Cypher 쿼리 생성
- [ ] Neo4j Graph Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

**Technical Details**:
```python
async def _graph_search(
    self,
    query: str,
    accessible_docs: list[str],
    top_k: int
) -> list[SearchResult]:
    # Cypher: 키워드가 포함된 Chunk와 연결된 Document 탐색
    cypher = """
    MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
    WHERE d.doc_uuid IN $doc_uuids
    AND c.text_preview CONTAINS $keyword
    RETURN c.chunk_uuid, c.text_preview, d.title, d.doc_uuid
    LIMIT $top_k
    """
```

**Tests**:
- `test_graph_search_basic()`
- `test_graph_search_relationship()`
- `test_graph_search_with_filter()`

---

### Task 3.1.4: Hybrid Search API 통합
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 3.1.1, 3.1.2, 3.1.3

**Description**:
3개 검색 방식을 병렬로 실행하고 결과를 통합하는 Hybrid Search를 구현합니다.

**Acceptance Criteria**:
- [ ] ACL 필터링 선실행
- [ ] asyncio.gather로 병렬 검색
- [ ] 결과 통합 (중복 제거, 점수 합산)
- [ ] 응답 시간 측정
- [ ] SearchResponse 반환

**Technical Details**:
```python
async def hybrid_search(self, request: SearchRequest) -> SearchResponse:
    start = time.time()

    # 1. ACL 필터링
    accessible_docs = await self.acl_service.get_accessible_documents(
        request.user_id, request.user_groups
    )

    # 2. 임베딩 생성
    embedding = self.embedding_service.encode([request.query])

    # 3. 병렬 검색
    tasks = [
        self._dense_search(embedding.dense[0], accessible_docs, request.top_k),
        self._sparse_search(embedding.sparse[0], accessible_docs, request.top_k),
        self._graph_search(request.query, accessible_docs, request.top_k),
    ]
    results = await asyncio.gather(*tasks)

    # 4. 결과 통합
    merged = self._merge_results(results, request.top_k)

    return SearchResponse(
        results=merged,
        total=len(merged),
        search_time_ms=(time.time() - start) * 1000
    )
```

**Tests**:
- `test_hybrid_search_all_types()`
- `test_hybrid_search_selected_types()`
- `test_hybrid_search_performance()`: P95 < 100ms

---

## Epic 3.2: Search API Router

### Task 3.2.1: Search Router 및 Schemas 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 3.1.4

**Description**:
Search API 엔드포인트와 Request/Response 스키마를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/api/routers/search.py` 생성
- [ ] `src/api/schemas/search.py` 생성
- [ ] `POST /api/v1/search` 엔드포인트
- [ ] SearchRequest 스키마 (query, user_id, user_groups, top_k, search_types)
- [ ] SearchResponse 스키마 (results, total, search_time_ms)
- [ ] 에러 핸들링 (400, 403, 500)

**Technical Details**:
```python
@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    search_service: SearchService = Depends(get_search_service)
):
    return await search_service.hybrid_search(request)
```

**Tests**:
- `test_search_endpoint_success()`
- `test_search_endpoint_empty_query()`
- `test_search_endpoint_no_access()`

---

### Task 3.2.2: Search 통합 테스트
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 3.2.1

**Description**:
Search 기능 전체 플로우를 검증하는 통합 테스트를 작성합니다.

**Acceptance Criteria**:
- [ ] `tests/integration/test_search_flow.py` 생성
- [ ] 테스트 데이터 시딩
- [ ] Dense Search 통합 테스트
- [ ] Sparse Search 통합 테스트
- [ ] Graph Search 통합 테스트
- [ ] Hybrid Search 통합 테스트
- [ ] ACL 필터링 통합 테스트

**Tests**:
- `test_search_flow_end_to_end()`
- `test_search_acl_filtering()`
- `test_search_performance()`

---

# Phase 4: 동기화 및 운영 기능

## Epic 4.1: Document Service 완성

### Task 4.1.1: Document Service 구현
- **Estimate**: 6h
- **Priority**: P0
- **Dependencies**: Task 2.3.3

**Description**:
문서 CRUD 비즈니스 로직을 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/document_service.py` 생성
- [ ] `create_document`: 임베딩 생성 + Saga 실행 + Kafka 이벤트
- [ ] `get_document`: PostgreSQL 조회
- [ ] `update_document`: 변경 사항 임베딩 + Saga 업데이트
- [ ] `delete_document`: Saga 삭제 + Kafka 이벤트

**Technical Details**:
```python
class DocumentService:
    async def create_document(self, request: DocumentCreateRequest) -> DocumentResponse:
        # 1. 임베딩 생성
        embeddings = self.embedding_service.encode([c.text for c in request.chunks])

        # 2. Saga 실행
        result = await self.saga_coordinator.execute_create_saga(document, chunks)

        # 3. Kafka 이벤트 발행
        await self.kafka_producer.send("document.created", {"doc_uuid": doc_uuid})

        return DocumentResponse(...)
```

**Tests**:
- `test_create_document_success()`
- `test_create_document_saga_failure()`
- `test_get_document()`
- `test_update_document()`
- `test_delete_document()`

---

### Task 4.1.2: Document Router 및 Schemas 구현
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 4.1.1

**Description**:
Document API 엔드포인트와 Request/Response 스키마를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/api/routers/documents.py` 생성
- [ ] `src/api/schemas/documents.py` 생성
- [ ] `POST /api/v1/documents` (Create)
- [ ] `GET /api/v1/documents/{doc_uuid}` (Read)
- [ ] `PUT /api/v1/documents/{doc_uuid}` (Update)
- [ ] `DELETE /api/v1/documents/{doc_uuid}` (Delete)
- [ ] 에러 핸들링

**Tests**:
- `test_create_document_endpoint()`
- `test_get_document_endpoint()`
- `test_update_document_endpoint()`
- `test_delete_document_endpoint()`

---

## Epic 4.2: Sync & Operations

### Task 4.2.1: Kafka Consumer 및 Sync Service 구현
- **Estimate**: 6h
- **Priority**: P1
- **Dependencies**: Task 2.1.4

**Description**:
Kafka 이벤트를 수신하여 변경 사항을 동기화하는 서비스를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/sync_service.py` 생성
- [ ] `src/repositories/kafka/consumer.py` 완성
- [ ] `document.updated` 이벤트 처리
- [ ] `document.deleted` 이벤트 처리
- [ ] 3개 저장소 동기화
- [ ] `sync.completed` 이벤트 발행

**Technical Details**:
```python
class SyncService:
    async def start_consumer(self):
        async for event in self.consumer.consume():
            if event["type"] == "document.updated":
                await self._handle_update(event)
            elif event["type"] == "document.deleted":
                await self._handle_delete(event)
```

**Tests**:
- `test_sync_update_event()`
- `test_sync_delete_event()`
- `test_sync_within_5_minutes()`

---

### Task 4.2.2: Health Check 및 Metrics 구현
- **Estimate**: 4h
- **Priority**: P1
- **Dependencies**: Task 2.1.1, 2.1.2, 2.1.3, 2.1.4

**Description**:
Health Check 및 Prometheus Metrics 엔드포인트를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/api/routers/health.py` 생성
- [ ] `src/api/routers/metrics.py` 생성
- [ ] `GET /api/v1/health`: 각 저장소 연결 상태 확인
- [ ] `GET /api/v1/metrics`: Prometheus 메트릭 노출
- [ ] 메트릭: 요청 수, 응답 시간, 에러 수

**Technical Details**:
```python
@router.get("/health")
async def health_check():
    checks = {
        "postgres": await postgres_client.ping(),
        "milvus": await milvus_client.ping(),
        "neo4j": await neo4j_client.ping(),
        "kafka": await kafka_client.ping(),
    }
    status = "healthy" if all(checks.values()) else "unhealthy"
    return {"status": status, "checks": checks}
```

**Tests**:
- `test_health_all_healthy()`
- `test_health_one_unhealthy()`
- `test_metrics_format()`

---

### Task 4.2.3: Audit Logger 구현
- **Estimate**: 4h
- **Priority**: P1
- **Dependencies**: Task 2.2.1

**Description**:
모든 조회/수정 이력을 기록하는 Audit Logger를 구현합니다.

**Acceptance Criteria**:
- [ ] `src/services/audit_service.py` 생성
- [ ] 검색 요청 로깅 (user_id, query, retrieved_docs)
- [ ] 문서 접근 로깅 (user_id, doc_uuid, action)
- [ ] 비동기 로깅 (성능 영향 최소화)

**Technical Details**:
```python
class AuditLogger:
    async def log_search(self, user_id: str, query: str, retrieved_docs: list[str]):
        await self.postgres_repo.create_audit_log(
            AuditLog(user_id=user_id, action="search", query_text=query, retrieved_docs=retrieved_docs)
        )

    async def log_document_access(self, user_id: str, doc_uuid: str, action: str):
        await self.postgres_repo.create_audit_log(
            AuditLog(user_id=user_id, action=action, doc_uuid=doc_uuid)
        )
```

**Tests**:
- `test_log_search()`
- `test_log_document_access()`

---

### Task 4.2.4: FastAPI 애플리케이션 통합
- **Estimate**: 4h
- **Priority**: P0
- **Dependencies**: Task 4.1.2, Task 3.2.1, Task 4.2.2

**Description**:
모든 Router를 통합하고 FastAPI 애플리케이션을 완성합니다.

**Acceptance Criteria**:
- [ ] `src/main.py` 완성
- [ ] 모든 Router 등록 (/documents, /search, /health, /metrics)
- [ ] 의존성 주입 설정 (`dependencies.py`)
- [ ] Lifespan 이벤트 (startup: DB 연결, shutdown: DB 종료)
- [ ] CORS 설정
- [ ] 예외 핸들러 등록

**Technical Details**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await postgres_client.connect()
    milvus_client.connect()
    # ...
    yield
    # Shutdown
    await postgres_client.disconnect()
    # ...

app = FastAPI(title="Knowledge Store", lifespan=lifespan)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(health_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
```

**Tests**:
- `test_app_startup()`
- `test_app_shutdown()`
- `test_all_endpoints_registered()`

---

### Task 4.2.5: E2E 테스트 작성
- **Estimate**: 6h
- **Priority**: P1
- **Dependencies**: Task 4.2.4

**Description**:
전체 시스템 플로우를 검증하는 E2E 테스트를 작성합니다.

**Acceptance Criteria**:
- [ ] `tests/e2e/test_full_cycle.py` 생성
- [ ] 문서 저장 → 검색 → 결과 확인
- [ ] 문서 수정 → 동기화 → 검색 결과 변경 확인
- [ ] 문서 삭제 → 검색 결과 미포함 확인
- [ ] ACL 권한 테스트

**Tests**:
- `test_full_document_lifecycle()`
- `test_search_after_create()`
- `test_search_after_update()`
- `test_search_after_delete()`
- `test_acl_enforcement()`

---

# Appendix

## Task Dependency Graph

```
Phase 1:
1.1.1 ──► 1.1.2
1.2.1 ──► 1.2.2 ──► 1.2.3
1.2.2 ──► 1.3.1
1.2.2 ──► 1.3.2
1.2.2 ──► 1.3.3
1.3.1, 1.3.2, 1.3.3 ──► 1.3.4

Phase 2:
1.3.1 ──► 2.1.1 ──► 2.2.1
1.3.2 ──► 2.1.2 ──► 2.2.2
1.3.3 ──► 2.1.3 ──► 2.2.3
1.2.2 ──► 2.1.4
2.2.1 ──► 2.3.2
2.2.1, 2.2.2, 2.2.3 ──► 2.3.3

Phase 3:
2.2.2, 2.3.1 ──► 3.1.1
2.2.2, 2.3.1 ──► 3.1.2
2.2.3 ──► 3.1.3
3.1.1, 3.1.2, 3.1.3 ──► 3.1.4 ──► 3.2.1 ──► 3.2.2

Phase 4:
2.3.3 ──► 4.1.1 ──► 4.1.2
2.1.4 ──► 4.2.1
2.1.* ──► 4.2.2
2.2.1 ──► 4.2.3
4.1.2, 3.2.1, 4.2.2 ──► 4.2.4 ──► 4.2.5
```

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total Tasks | 30 |
| P0 Tasks | 24 |
| P1 Tasks | 6 |
| Total Hours | 160h |
| Average Task Size | 5.3h |
| Tasks 4-6h | 20 |
| Tasks 6-8h | 10 |

## INVEST Checklist

- ✅ **I**ndependent: 각 Task는 독립적으로 완료 가능
- ✅ **N**egotiable: 범위 조정 가능
- ✅ **V**aluable: 각 Task가 비즈니스 가치 제공
- ✅ **E**stimable: 모든 Task에 시간 추정치 있음
- ✅ **S**mall: 모든 Task ≤ 8h
- ✅ **T**estable: 모든 Task에 테스트 기준 있음

---

## Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial task breakdown |
