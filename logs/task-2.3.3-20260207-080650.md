# Task 2.3.3: Saga Coordinator 구현

## 작업 정보
- **Task ID**: 2.3.3
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 08:06:50
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/19
- **Task Plan**: docs/task-plans/task-2.3.3-plan.md

## 작업 개요
3개 저장소(PostgreSQL, Milvus, Neo4j)에 대한 분산 트랜잭션을 관리하는 Saga Coordinator를 구현합니다.

## 생성된 파일

### 1. Saga Models
**파일**: `src/services/saga/models.py`

#### StepStatus Enum
```python
class StepStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    COMPENSATED = "compensated"
    FAILED = "failed"
```

#### StepResult Dataclass
```python
@dataclass
class StepResult:
    success: bool
    step_name: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
```

#### SagaContext Dataclass
```python
@dataclass
class SagaContext:
    doc_uuid: str
    document: Any | None = None
    chunks: list[Any] = field(default_factory=list)
    embeddings: Any | None = None
    results: dict[str, Any] = field(default_factory=dict)
```

#### SagaResult Dataclass
```python
@dataclass
class SagaResult:
    success: bool
    doc_uuid: str
    executed_steps: list[str]
    compensated_steps: list[str]
    error: str | None
    step_results: dict[str, StepResult]
```

#### SagaStep Protocol
```python
class SagaStep(Protocol):
    @property
    def name(self) -> str: ...
    async def execute(self, context: SagaContext) -> StepResult: ...
    async def compensate(self, context: SagaContext) -> StepResult: ...
```

### 2. Saga Steps
**파일**: `src/services/saga/steps.py`

#### Create Steps
- `PostgresCreateStep`: Document + Chunks PostgreSQL 저장
- `MilvusCreateStep`: Vector Milvus 저장
- `Neo4jCreateStep`: Graph 노드/엣지 생성

#### Delete Steps
- `Neo4jDeleteStep`: Graph 삭제 (백업 저장)
- `MilvusDeleteStep`: Vector 삭제
- `PostgresDeleteStep`: Document 삭제 (백업 저장)

#### Update Steps
- `PostgresUpdateStep`: Document 업데이트 + Chunks 교체

### 3. Saga Coordinator
**파일**: `src/services/saga/coordinator.py`

#### SagaCoordinator 클래스
- **Methods**:
  - `execute_create_saga(document, chunks, embeddings) -> SagaResult`
    - 순서: PostgreSQL → Milvus → Neo4j
    - 보상: Neo4j → Milvus → PostgreSQL
  - `execute_delete_saga(doc_uuid) -> SagaResult`
    - 순서: Neo4j → Milvus → PostgreSQL
    - 보상: PostgreSQL → Milvus → Neo4j
  - `execute_update_saga(doc_uuid, document, chunks) -> SagaResult`
    - Phase 1: Delete old (Neo4j → Milvus)
    - Phase 2: Update PostgreSQL
    - Phase 3: Create new (Milvus → Neo4j)

#### Factory Pattern
- `get_saga_coordinator(postgres, milvus, neo4j, embedding_service) -> SagaCoordinator`
- `close_saga_coordinator() -> None`
- `reset_saga_coordinator() -> None`

**exports 업데이트**: `src/services/saga/__init__.py`

### 4. Unit Tests
**파일**: `tests/unit/test_services/test_saga_coordinator.py`

테스트 클래스:
- `TestStepResult`: 2개 테스트
- `TestSagaResult`: 3개 테스트
- `TestSagaContext`: 3개 테스트
- `TestStepStatus`: 1개 테스트
- `TestCreateSaga`: 5개 테스트
- `TestDeleteSaga`: 3개 테스트
- `TestUpdateSaga`: 1개 테스트
- `TestPostgresCreateStep`: 2개 테스트
- `TestMilvusCreateStep`: 1개 테스트
- `TestNeo4jCreateStep`: 1개 테스트
- `TestSingletonFactory`: 5개 테스트

**총 27개 테스트, 100% PASSED**

## 기술적 특징

### 1. Saga Pattern Orchestration
```python
# Create Saga 순서
PostgresCreateStep → MilvusCreateStep → Neo4jCreateStep

# 실패 시 역순 보상
if MilvusCreateStep fails:
    PostgresCreateStep.compensate()

if Neo4jCreateStep fails:
    MilvusCreateStep.compensate()
    PostgresCreateStep.compensate()
```

### 2. Automatic Compensation
```python
async def _execute_steps(self, steps, context) -> SagaResult:
    executed = []
    for step in steps:
        result = await step.execute(context)
        if result.success:
            executed.append(step)
        else:
            # Compensate in reverse order
            await self._compensate_steps(reversed(executed), context, result)
            break
    return result
```

### 3. Context-based Data Passing
```python
# Step 간 데이터 전달
context.set_result("postgres_create", {"doc": doc, "chunks": chunks})

# 보상 시 데이터 활용
backup = context.get_result("postgres_delete_backup")
await repository.create_document(backup["doc"])
```

### 4. Logging for Observability
```python
logger.info(f"Executing saga step: {step.name}")
logger.error(f"Step failed: {step.name} - {step_result.error}")
logger.info(f"Compensating saga step: {step.name}")
```

## 테스트 결과

```
============================== test session starts ==============================
27 passed in 0.24s

Coverage:
- src/services/saga/models.py: 94%
- src/services/saga/coordinator.py: 88%
- src/services/saga/steps.py: 72%
```

## 해결된 이슈

### 1. MilvusChunk 필드 불일치
- **문제**: `chunk_no` 필드가 MilvusChunk에 존재하지 않음
- **해결**: MilvusCreateStep에서 `chunk_no` 필드 제거

### 2. Unused Imports
- **문제**: coordinator.py에서 StepResult 미사용
- **해결**: import 제거

## Saga 실행 예시

### Create Saga 성공
```python
coordinator = SagaCoordinator(postgres, milvus, neo4j, embedder)
result = await coordinator.execute_create_saga(document, chunks)
# result.success = True
# result.executed_steps = ["postgres_create", "milvus_create", "neo4j_create"]
# result.compensated_steps = []
```

### Create Saga 실패 (Milvus 오류)
```python
result = await coordinator.execute_create_saga(document, chunks)
# result.success = False
# result.error = "Step 'milvus_create' failed: Connection refused"
# result.executed_steps = ["postgres_create"]
# result.compensated_steps = ["postgres_create"]  # 자동 롤백
```

## 다음 단계
- Task 2.3.4: Chunking Service 구현
- Task 2.3.5: Entity Extraction Service 구현
