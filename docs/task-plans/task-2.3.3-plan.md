# Task Execution Plan: 2.3.3 - Saga Coordinator 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.3.3 |
| **Task Name** | Saga Coordinator 구현 |
| **Estimate** | 8h |
| **Priority** | P0 |
| **Dependencies** | Task 2.2.1, 2.2.2, 2.2.3 |

### Description
3개 저장소(PostgreSQL, Milvus, Neo4j)에 대한 분산 트랜잭션을 관리하는 Saga Coordinator를 구현합니다.

### Acceptance Criteria
- [ ] `src/services/saga/coordinator.py` 생성
- [ ] `src/services/saga/steps.py` 생성
- [ ] Create Saga (PostgreSQL → Milvus → Neo4j)
- [ ] Delete Saga (Neo4j → Milvus → PostgreSQL)
- [ ] 실패 시 보상 트랜잭션 실행
- [ ] Saga 실행 결과 반환 (성공/실패/보상 내역)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.5 Saga Pattern
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 6 NFR-1

### 2.2 Saga Pattern 개요
```
Saga = 일련의 로컬 트랜잭션 + 보상 트랜잭션

Create Saga:
1. PostgreSQL: Document + Chunks 저장 → (실패 시) 삭제
2. Milvus: Vectors 저장 → (실패 시) 삭제
3. Neo4j: Graph 노드/엣지 생성 → (실패 시) 삭제

Delete Saga (역순):
1. Neo4j: Graph 삭제 → (실패 시) 복원
2. Milvus: Vectors 삭제 → (실패 시) 복원
3. PostgreSQL: Document 삭제 → (실패 시) 복원
```

### 2.3 설계 결정
1. **Orchestration 방식**: 중앙 Coordinator가 순서 제어
2. **보상 전략**: 역순 보상 (last-executed-first-compensated)
3. **Step 인터페이스**: execute/compensate 메서드
4. **상태 추적**: SagaResult에 실행 내역 기록
5. **에러 처리**: 보상 실패 시에도 계속 진행 (최대한 롤백)

### 2.4 클래스 구조
```
SagaStep (Protocol)
├── name: str
├── execute(context) -> StepResult
└── compensate(context) -> StepResult

SagaCoordinator
├── execute_create_saga(document, chunks) -> SagaResult
├── execute_delete_saga(doc_uuid) -> SagaResult
└── execute_update_saga(doc_uuid, updates) -> SagaResult

SagaResult
├── success: bool
├── doc_uuid: str
├── executed_steps: list[str]
├── compensated_steps: list[str]
├── error: str | None
└── step_results: dict[str, Any]

SagaContext
├── document: Document
├── chunks: list[Chunk]
├── doc_uuid: str
└── results: dict[str, Any]
```

### 2.5 실행 순서
```
Create:
PostgresCreateStep → MilvusCreateStep → Neo4jCreateStep

Delete:
Neo4jDeleteStep → MilvusDeleteStep → PostgresDeleteStep

Update:
1. Delete old (Neo4j → Milvus)
2. Create new (PostgreSQL update → Milvus → Neo4j)
```

---

## 3. Implementation Steps

### Step 1: 기본 인터페이스 및 모델 정의 (1h)

**작업 내용:**
1. SagaStep Protocol 정의
2. SagaResult, StepResult 모델
3. SagaContext 정의

**src/services/saga/models.py:**
```python
"""Saga models and types."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class StepStatus(str, Enum):
    """Status of a saga step."""

    PENDING = "pending"
    EXECUTED = "executed"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class StepResult:
    """Result of a saga step execution."""

    success: bool
    step_name: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class SagaContext:
    """Context passed between saga steps."""

    doc_uuid: str
    document: Any | None = None  # Document model
    chunks: list[Any] = field(default_factory=list)  # Chunk models
    embeddings: Any | None = None  # EmbeddingResult
    results: dict[str, Any] = field(default_factory=dict)

    def set_result(self, step_name: str, data: Any) -> None:
        """Store step result in context."""
        self.results[step_name] = data

    def get_result(self, step_name: str) -> Any:
        """Get step result from context."""
        return self.results.get(step_name)


@dataclass
class SagaResult:
    """Result of saga execution."""

    success: bool
    doc_uuid: str
    executed_steps: list[str] = field(default_factory=list)
    compensated_steps: list[str] = field(default_factory=list)
    error: str | None = None
    step_results: dict[str, StepResult] = field(default_factory=dict)

    def add_executed(self, step_name: str, result: StepResult) -> None:
        """Record executed step."""
        self.executed_steps.append(step_name)
        self.step_results[step_name] = result

    def add_compensated(self, step_name: str) -> None:
        """Record compensated step."""
        self.compensated_steps.append(step_name)


class SagaStep(Protocol):
    """Protocol for saga step."""

    @property
    def name(self) -> str:
        """Step name for logging."""
        ...

    async def execute(self, context: SagaContext) -> StepResult:
        """Execute the step."""
        ...

    async def compensate(self, context: SagaContext) -> StepResult:
        """Compensate (rollback) the step."""
        ...
```

**완료 기준:**
- [ ] StepResult, StepStatus 정의
- [ ] SagaContext 정의
- [ ] SagaResult 정의
- [ ] SagaStep Protocol 정의

---

### Step 2: Saga Step 구현 - Create (2h)

**작업 내용:**
1. PostgresCreateStep 구현
2. MilvusCreateStep 구현
3. Neo4jCreateStep 구현

**src/services/saga/steps.py:**
```python
"""Saga step implementations."""
from typing import Any

from src.services.saga.models import SagaContext, StepResult


class PostgresCreateStep:
    """Step to create document in PostgreSQL."""

    name = "postgres_create"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Create document and chunks in PostgreSQL."""
        try:
            # Create document
            doc = await self._repository.create_document(context.document)

            # Create chunks
            chunks = await self._repository.create_chunks(context.chunks)

            context.set_result(self.name, {"doc": doc, "chunks": chunks})

            return StepResult(
                success=True,
                step_name=self.name,
                data={"doc_uuid": doc.doc_uuid, "chunk_count": len(chunks)},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete document and chunks from PostgreSQL."""
        try:
            await self._repository.delete_document(context.doc_uuid)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class MilvusCreateStep:
    """Step to create vectors in Milvus."""

    name = "milvus_create"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Insert vectors into Milvus."""
        try:
            if context.embeddings is None:
                return StepResult(
                    success=False,
                    step_name=self.name,
                    error="No embeddings in context",
                )

            # Build vector data
            vectors = []
            for i, chunk in enumerate(context.chunks):
                vectors.append({
                    "chunk_uuid": chunk.chunk_uuid,
                    "doc_uuid": context.doc_uuid,
                    "dense_embedding": context.embeddings.dense[i],
                    "sparse_embedding": context.embeddings.sparse[i],
                })

            # Insert vectors
            chunk_uuids = await self._repository.insert_vectors(vectors)

            context.set_result(self.name, {"chunk_uuids": chunk_uuids})

            return StepResult(
                success=True,
                step_name=self.name,
                data={"inserted_count": len(chunk_uuids)},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete vectors from Milvus."""
        try:
            chunk_uuids = [c.chunk_uuid for c in context.chunks]
            await self._repository.delete_vectors(chunk_uuids)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class Neo4jCreateStep:
    """Step to create graph nodes in Neo4j."""

    name = "neo4j_create"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Create document and chunk nodes in Neo4j."""
        try:
            # Create document node
            await self._repository.create_document_node(context.document)

            # Create chunk nodes
            await self._repository.create_chunk_nodes(context.chunks)

            # Create CONTAINS edges
            chunk_uuids = [c.chunk_uuid for c in context.chunks]
            await self._repository.create_contains_edges(
                context.doc_uuid, chunk_uuids
            )

            return StepResult(
                success=True,
                step_name=self.name,
                data={"node_count": 1 + len(context.chunks)},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete document graph from Neo4j."""
        try:
            await self._repository.delete_document_graph(context.doc_uuid)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )
```

**완료 기준:**
- [ ] PostgresCreateStep 구현
- [ ] MilvusCreateStep 구현
- [ ] Neo4jCreateStep 구현

---

### Step 3: Saga Step 구현 - Delete (1.5h)

**작업 내용:**
1. Neo4jDeleteStep 구현
2. MilvusDeleteStep 구현
3. PostgresDeleteStep 구현

**src/services/saga/steps.py (계속):**
```python
class Neo4jDeleteStep:
    """Step to delete graph from Neo4j."""

    name = "neo4j_delete"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete document graph from Neo4j."""
        try:
            # Get graph data for potential compensation
            graph_data = await self._repository.get_document_graph(context.doc_uuid)
            context.set_result(f"{self.name}_backup", graph_data)

            # Delete graph
            await self._repository.delete_document_graph(context.doc_uuid)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted": True},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore graph in Neo4j."""
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup:
                await self._repository.restore_document_graph(backup)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class MilvusDeleteStep:
    """Step to delete vectors from Milvus."""

    name = "milvus_delete"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete vectors from Milvus."""
        try:
            # Get vectors for potential compensation
            vectors = await self._repository.get_vectors_by_doc(context.doc_uuid)
            context.set_result(f"{self.name}_backup", vectors)

            # Delete vectors
            chunk_uuids = [v["chunk_uuid"] for v in vectors]
            await self._repository.delete_vectors(chunk_uuids)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted_count": len(chunk_uuids)},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore vectors in Milvus."""
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup:
                await self._repository.insert_vectors(backup)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class PostgresDeleteStep:
    """Step to delete document from PostgreSQL."""

    name = "postgres_delete"

    def __init__(self, repository: Any) -> None:
        """Initialize with repository."""
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete document from PostgreSQL."""
        try:
            # Get document for potential compensation
            doc = await self._repository.get_document(context.doc_uuid)
            chunks = await self._repository.get_chunks_by_doc(context.doc_uuid)
            context.set_result(f"{self.name}_backup", {"doc": doc, "chunks": chunks})

            # Delete document (cascades to chunks)
            await self._repository.delete_document(context.doc_uuid)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted": True},
            )
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore document in PostgreSQL."""
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup:
                await self._repository.create_document(backup["doc"])
                await self._repository.create_chunks(backup["chunks"])
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )
```

**완료 기준:**
- [ ] Neo4jDeleteStep 구현
- [ ] MilvusDeleteStep 구현
- [ ] PostgresDeleteStep 구현
- [ ] 백업/복원 로직 구현

---

### Step 4: Saga Coordinator 구현 (2h)

**작업 내용:**
1. SagaCoordinator 클래스
2. execute_create_saga 구현
3. execute_delete_saga 구현
4. execute_update_saga 구현

**src/services/saga/coordinator.py:**
```python
"""Saga coordinator for distributed transactions."""
import logging
from typing import Any

from src.services.saga.models import SagaContext, SagaResult, SagaStep
from src.services.saga.steps import (
    MilvusCreateStep,
    MilvusDeleteStep,
    Neo4jCreateStep,
    Neo4jDeleteStep,
    PostgresCreateStep,
    PostgresDeleteStep,
)

logger = logging.getLogger(__name__)


class SagaCoordinator:
    """Coordinator for saga-based distributed transactions."""

    def __init__(
        self,
        postgres_repo: Any,
        milvus_repo: Any,
        neo4j_repo: Any,
        embedding_service: Any | None = None,
    ) -> None:
        """Initialize saga coordinator.

        Args:
            postgres_repo: PostgreSQL repository
            milvus_repo: Milvus repository
            neo4j_repo: Neo4j repository
            embedding_service: Embedding service (optional, for create/update)
        """
        self._postgres_repo = postgres_repo
        self._milvus_repo = milvus_repo
        self._neo4j_repo = neo4j_repo
        self._embedding_service = embedding_service

    def _get_create_steps(self) -> list[SagaStep]:
        """Get steps for create saga."""
        return [
            PostgresCreateStep(self._postgres_repo),
            MilvusCreateStep(self._milvus_repo),
            Neo4jCreateStep(self._neo4j_repo),
        ]

    def _get_delete_steps(self) -> list[SagaStep]:
        """Get steps for delete saga."""
        return [
            Neo4jDeleteStep(self._neo4j_repo),
            MilvusDeleteStep(self._milvus_repo),
            PostgresDeleteStep(self._postgres_repo),
        ]

    async def _execute_steps(
        self,
        steps: list[SagaStep],
        context: SagaContext,
    ) -> SagaResult:
        """Execute saga steps with compensation on failure.

        Args:
            steps: List of steps to execute
            context: Saga context

        Returns:
            SagaResult with execution details
        """
        result = SagaResult(success=True, doc_uuid=context.doc_uuid)
        executed: list[SagaStep] = []

        for step in steps:
            logger.info(f"Executing step: {step.name}")
            step_result = await step.execute(context)

            if step_result.success:
                result.add_executed(step.name, step_result)
                executed.append(step)
            else:
                logger.error(f"Step failed: {step.name} - {step_result.error}")
                result.success = False
                result.error = f"Step '{step.name}' failed: {step_result.error}"

                # Compensate in reverse order
                await self._compensate_steps(list(reversed(executed)), context, result)
                break

        return result

    async def _compensate_steps(
        self,
        steps: list[SagaStep],
        context: SagaContext,
        result: SagaResult,
    ) -> None:
        """Compensate executed steps in reverse order.

        Args:
            steps: Steps to compensate (already reversed)
            context: Saga context
            result: SagaResult to update
        """
        for step in steps:
            logger.info(f"Compensating step: {step.name}")
            try:
                comp_result = await step.compensate(context)
                if comp_result.success:
                    result.add_compensated(step.name)
                else:
                    logger.error(
                        f"Compensation failed for {step.name}: {comp_result.error}"
                    )
            except Exception as e:
                logger.error(f"Compensation exception for {step.name}: {e}")

    async def execute_create_saga(
        self,
        document: Any,
        chunks: list[Any],
    ) -> SagaResult:
        """Execute create saga for document storage.

        Order: PostgreSQL → Milvus → Neo4j
        Compensation: Neo4j → Milvus → PostgreSQL

        Args:
            document: Document to create
            chunks: Chunks to create

        Returns:
            SagaResult with execution details
        """
        # Generate embeddings if service available
        embeddings = None
        if self._embedding_service:
            texts = [c.text for c in chunks]
            embeddings = self._embedding_service.encode(texts)

        context = SagaContext(
            doc_uuid=document.doc_uuid,
            document=document,
            chunks=chunks,
            embeddings=embeddings,
        )

        steps = self._get_create_steps()
        return await self._execute_steps(steps, context)

    async def execute_delete_saga(self, doc_uuid: str) -> SagaResult:
        """Execute delete saga for document removal.

        Order: Neo4j → Milvus → PostgreSQL
        Compensation: PostgreSQL → Milvus → Neo4j

        Args:
            doc_uuid: Document UUID to delete

        Returns:
            SagaResult with execution details
        """
        context = SagaContext(doc_uuid=doc_uuid)

        steps = self._get_delete_steps()
        return await self._execute_steps(steps, context)

    async def execute_update_saga(
        self,
        doc_uuid: str,
        document: Any,
        chunks: list[Any],
    ) -> SagaResult:
        """Execute update saga (delete old + create new).

        Args:
            doc_uuid: Document UUID to update
            document: Updated document
            chunks: Updated chunks

        Returns:
            SagaResult with execution details
        """
        # First, delete old data from Milvus and Neo4j
        delete_context = SagaContext(doc_uuid=doc_uuid)
        delete_steps = [
            Neo4jDeleteStep(self._neo4j_repo),
            MilvusDeleteStep(self._milvus_repo),
        ]

        delete_result = await self._execute_steps(delete_steps, delete_context)
        if not delete_result.success:
            return delete_result

        # Then, update PostgreSQL and create new in Milvus/Neo4j
        embeddings = None
        if self._embedding_service:
            texts = [c.text for c in chunks]
            embeddings = self._embedding_service.encode(texts)

        # Update PostgreSQL (not create)
        await self._postgres_repo.update_document(doc_uuid, document)
        await self._postgres_repo.delete_chunks_by_doc(doc_uuid)
        await self._postgres_repo.create_chunks(chunks)

        # Create in Milvus and Neo4j
        create_context = SagaContext(
            doc_uuid=doc_uuid,
            document=document,
            chunks=chunks,
            embeddings=embeddings,
        )
        create_steps = [
            MilvusCreateStep(self._milvus_repo),
            Neo4jCreateStep(self._neo4j_repo),
        ]

        create_result = await self._execute_steps(create_steps, create_context)

        # Merge results
        result = SagaResult(
            success=create_result.success,
            doc_uuid=doc_uuid,
            executed_steps=delete_result.executed_steps + create_result.executed_steps,
            compensated_steps=create_result.compensated_steps,
            error=create_result.error,
        )

        return result
```

**완료 기준:**
- [ ] SagaCoordinator 클래스 구현
- [ ] execute_create_saga 구현
- [ ] execute_delete_saga 구현
- [ ] execute_update_saga 구현
- [ ] 보상 트랜잭션 로직

---

### Step 5: Factory 및 테스트 (1.5h)

**작업 내용:**
1. Factory 함수
2. __init__.py 업데이트
3. 테스트 작성

**src/services/saga/__init__.py:**
```python
"""Saga pattern implementation for distributed transactions."""
from src.services.saga.coordinator import SagaCoordinator
from src.services.saga.models import SagaContext, SagaResult, SagaStep, StepResult

__all__ = [
    "SagaCoordinator",
    "SagaContext",
    "SagaResult",
    "SagaStep",
    "StepResult",
]
```

**tests/unit/test_services/test_saga_coordinator.py:**
```python
"""Tests for Saga Coordinator."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.saga.coordinator import SagaCoordinator
from src.services.saga.models import SagaContext, SagaResult


@pytest.fixture
def mock_repos() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Create mock repositories."""
    postgres = MagicMock()
    milvus = MagicMock()
    neo4j = MagicMock()
    return postgres, milvus, neo4j


@pytest.fixture
def coordinator(mock_repos: tuple) -> SagaCoordinator:
    """Create coordinator with mock repos."""
    postgres, milvus, neo4j = mock_repos
    return SagaCoordinator(postgres, milvus, neo4j)


class TestSagaCoordinator:
    """Tests for SagaCoordinator."""

    async def test_create_saga_success(
        self,
        coordinator: SagaCoordinator,
        mock_repos: tuple,
    ) -> None:
        """Test successful create saga."""
        postgres, milvus, neo4j = mock_repos

        # Setup mocks
        mock_doc = MagicMock(doc_uuid="test-uuid")
        mock_chunk = MagicMock(chunk_uuid="chunk-1", text="test")

        postgres.create_document = AsyncMock(return_value=mock_doc)
        postgres.create_chunks = AsyncMock(return_value=[mock_chunk])
        milvus.insert_vectors = AsyncMock(return_value=["chunk-1"])
        neo4j.create_document_node = AsyncMock()
        neo4j.create_chunk_nodes = AsyncMock()
        neo4j.create_contains_edges = AsyncMock()

        # Mock embedding service
        mock_embedding = MagicMock()
        mock_embedding.encode.return_value = MagicMock(
            dense=[[0.1] * 1024],
            sparse=[{1: 0.5}],
        )
        coordinator._embedding_service = mock_embedding

        result = await coordinator.execute_create_saga(mock_doc, [mock_chunk])

        assert result.success
        assert len(result.executed_steps) == 3
        assert len(result.compensated_steps) == 0

    async def test_create_saga_milvus_fail_compensate(
        self,
        coordinator: SagaCoordinator,
        mock_repos: tuple,
    ) -> None:
        """Test create saga with Milvus failure triggers compensation."""
        postgres, milvus, neo4j = mock_repos

        mock_doc = MagicMock(doc_uuid="test-uuid")
        mock_chunk = MagicMock(chunk_uuid="chunk-1", text="test")

        # Postgres succeeds
        postgres.create_document = AsyncMock(return_value=mock_doc)
        postgres.create_chunks = AsyncMock(return_value=[mock_chunk])
        postgres.delete_document = AsyncMock()

        # Milvus fails
        milvus.insert_vectors = AsyncMock(side_effect=Exception("Milvus error"))

        # Mock embedding
        mock_embedding = MagicMock()
        mock_embedding.encode.return_value = MagicMock(
            dense=[[0.1] * 1024],
            sparse=[{1: 0.5}],
        )
        coordinator._embedding_service = mock_embedding

        result = await coordinator.execute_create_saga(mock_doc, [mock_chunk])

        assert not result.success
        assert "milvus_create" in result.error
        assert "postgres_create" in result.executed_steps
        assert "postgres_create" in result.compensated_steps

    async def test_delete_saga_success(
        self,
        coordinator: SagaCoordinator,
        mock_repos: tuple,
    ) -> None:
        """Test successful delete saga."""
        postgres, milvus, neo4j = mock_repos

        neo4j.get_document_graph = AsyncMock(return_value={})
        neo4j.delete_document_graph = AsyncMock()
        milvus.get_vectors_by_doc = AsyncMock(return_value=[])
        milvus.delete_vectors = AsyncMock()
        postgres.get_document = AsyncMock(return_value=MagicMock())
        postgres.get_chunks_by_doc = AsyncMock(return_value=[])
        postgres.delete_document = AsyncMock()

        result = await coordinator.execute_delete_saga("test-uuid")

        assert result.success
        assert len(result.executed_steps) == 3


class TestSagaResult:
    """Tests for SagaResult."""

    def test_add_executed(self) -> None:
        """Test adding executed step."""
        result = SagaResult(success=True, doc_uuid="test")
        result.add_executed("step1", MagicMock(success=True))
        assert "step1" in result.executed_steps

    def test_add_compensated(self) -> None:
        """Test adding compensated step."""
        result = SagaResult(success=False, doc_uuid="test")
        result.add_compensated("step1")
        assert "step1" in result.compensated_steps
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] __init__.py 업데이트
- [ ] Create Saga 성공 테스트
- [ ] Create Saga 실패/보상 테스트
- [ ] Delete Saga 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_saga_success` | 모든 Step 성공 | success=True |
| `test_create_saga_milvus_fail` | Milvus 실패 | Postgres 보상 |
| `test_create_saga_neo4j_fail` | Neo4j 실패 | Milvus, Postgres 보상 |
| `test_delete_saga_success` | 모든 Step 성공 | success=True |
| `test_delete_saga_partial_fail` | 부분 실패 | 보상 실행 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_document_all_stores` | 실제 3개 저장소 | 모든 저장소에 데이터 |
| `test_create_rollback` | 실패 시 롤백 | 어떤 저장소에도 데이터 없음 |
| `test_delete_document_all_stores` | 실제 삭제 | 모든 저장소에서 삭제 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 보상 실패 | High | Low | 보상 실패 로깅, 수동 복구 가이드 |
| 네트워크 분할 | High | Low | 타임아웃 설정, 재시도 로직 |
| 부분 상태 | High | Medium | Saga 상태 추적, 복구 스크립트 |
| 성능 병목 | Medium | Medium | 병렬 실행 고려 (순서 무관 시) |

---

## 6. Definition of Done

- [ ] `src/services/saga/models.py` 구현
- [ ] `src/services/saga/steps.py` 구현
- [ ] `src/services/saga/coordinator.py` 구현
- [ ] Create Saga 구현 (PostgreSQL → Milvus → Neo4j)
- [ ] Delete Saga 구현 (Neo4j → Milvus → PostgreSQL)
- [ ] Update Saga 구현
- [ ] 보상 트랜잭션 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 인터페이스 및 모델 | 1h | - |
| Step 2: Create Steps | 2h | - |
| Step 3: Delete Steps | 1.5h | - |
| Step 4: Coordinator | 2h | - |
| Step 5: Factory 및 테스트 | 1.5h | - |
| **Total** | **8h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
