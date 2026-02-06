"""Tests for Saga Coordinator."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.saga.coordinator import (
    SagaCoordinator,
    close_saga_coordinator,
    get_saga_coordinator,
    reset_saga_coordinator,
)
from src.services.saga.models import SagaContext, SagaResult, StepResult, StepStatus
from src.services.saga.steps import (
    MilvusCreateStep,
    Neo4jCreateStep,
    PostgresCreateStep,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_postgres() -> MagicMock:
    """Create mock PostgreSQL repository."""
    repo = MagicMock()
    repo.create_document = AsyncMock()
    repo.create_chunks = AsyncMock()
    repo.get_document = AsyncMock()
    repo.get_chunks_by_doc = AsyncMock()
    repo.update_document = AsyncMock()
    repo.delete_document = AsyncMock()
    repo.delete_chunks_by_doc = AsyncMock()
    return repo


@pytest.fixture
def mock_milvus() -> MagicMock:
    """Create mock Milvus repository."""
    repo = MagicMock()
    repo.insert_chunks = AsyncMock()
    repo.delete_by_doc_uuid = AsyncMock()
    repo.delete_by_chunk_uuids = AsyncMock()
    return repo


@pytest.fixture
def mock_neo4j() -> MagicMock:
    """Create mock Neo4j repository."""
    repo = MagicMock()
    repo.create_document_node = AsyncMock()
    repo.create_chunk_nodes = AsyncMock()
    repo.create_contains_edges = AsyncMock()
    repo.get_document_graph = AsyncMock(return_value={})
    repo.delete_document_graph = AsyncMock()
    return repo


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    service = MagicMock()
    service.encode.return_value = MagicMock(
        dense=[[0.1] * 1024],
        sparse=[MagicMock()],
    )
    return service


@pytest.fixture
def coordinator(
    mock_postgres: MagicMock,
    mock_milvus: MagicMock,
    mock_neo4j: MagicMock,
) -> SagaCoordinator:
    """Create coordinator with mock repos."""
    return SagaCoordinator(mock_postgres, mock_milvus, mock_neo4j)


@pytest.fixture
def mock_document() -> MagicMock:
    """Create mock document."""
    doc = MagicMock()
    doc.doc_uuid = "test-doc-uuid"
    doc.title = "Test Document"
    doc.source = "file"
    doc.security_level = "internal"
    return doc


@pytest.fixture
def mock_chunks() -> list[MagicMock]:
    """Create mock chunks."""
    chunks = []
    for i in range(2):
        chunk = MagicMock()
        chunk.chunk_uuid = f"chunk-{i}"
        chunk.chunk_text = f"Test chunk {i} content"
        chunk.chunk_no = i
        chunk.section_path = None
        chunks.append(chunk)
    return chunks


# =============================================================================
# Test StepResult and SagaResult Models
# =============================================================================


class TestStepResult:
    """Tests for StepResult model."""

    def test_create_success_result(self) -> None:
        """Test creating successful step result."""
        result = StepResult(
            success=True,
            step_name="test_step",
            data={"key": "value"},
        )

        assert result.success is True
        assert result.step_name == "test_step"
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_create_failure_result(self) -> None:
        """Test creating failed step result."""
        result = StepResult(
            success=False,
            step_name="test_step",
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"


class TestSagaResult:
    """Tests for SagaResult model."""

    def test_create_result(self) -> None:
        """Test creating saga result."""
        result = SagaResult(success=True, doc_uuid="doc-123")

        assert result.success is True
        assert result.doc_uuid == "doc-123"
        assert result.executed_steps == []
        assert result.compensated_steps == []
        assert result.error is None

    def test_add_executed(self) -> None:
        """Test adding executed step."""
        result = SagaResult(success=True, doc_uuid="doc-123")
        step_result = StepResult(success=True, step_name="step1")

        result.add_executed("step1", step_result)

        assert "step1" in result.executed_steps
        assert "step1" in result.step_results

    def test_add_compensated(self) -> None:
        """Test adding compensated step."""
        result = SagaResult(success=False, doc_uuid="doc-123")

        result.add_compensated("step1")

        assert "step1" in result.compensated_steps


class TestSagaContext:
    """Tests for SagaContext model."""

    def test_create_context(self) -> None:
        """Test creating saga context."""
        context = SagaContext(doc_uuid="doc-123")

        assert context.doc_uuid == "doc-123"
        assert context.document is None
        assert context.chunks == []
        assert context.embeddings is None
        assert context.results == {}

    def test_set_and_get_result(self) -> None:
        """Test setting and getting result."""
        context = SagaContext(doc_uuid="doc-123")

        context.set_result("step1", {"data": "value"})
        result = context.get_result("step1")

        assert result == {"data": "value"}

    def test_get_missing_result(self) -> None:
        """Test getting missing result."""
        context = SagaContext(doc_uuid="doc-123")

        result = context.get_result("nonexistent")

        assert result is None


class TestStepStatus:
    """Tests for StepStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert StepStatus.PENDING.value == "pending"
        assert StepStatus.EXECUTED.value == "executed"
        assert StepStatus.COMPENSATED.value == "compensated"
        assert StepStatus.FAILED.value == "failed"


# =============================================================================
# Test Create Saga
# =============================================================================


class TestCreateSaga:
    """Tests for create saga execution."""

    @pytest.mark.asyncio
    async def test_create_saga_success(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test successful create saga."""
        # Setup mocks
        mock_postgres.create_document.return_value = mock_document
        mock_postgres.create_chunks.return_value = mock_chunks
        mock_milvus.insert_chunks.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_document_node.return_value = "test-doc-uuid"
        mock_neo4j.create_chunk_nodes.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_contains_edges.return_value = 2

        # Add embedding service
        coordinator._embedding_service = mock_embedding_service
        mock_embedding_service.encode.return_value = MagicMock(
            dense=[[0.1] * 1024, [0.2] * 1024],
            sparse=[MagicMock(), MagicMock()],
        )

        result = await coordinator.execute_create_saga(mock_document, mock_chunks)

        assert result.success is True
        assert len(result.executed_steps) == 3
        assert "postgres_create" in result.executed_steps
        assert "milvus_create" in result.executed_steps
        assert "neo4j_create" in result.executed_steps
        assert len(result.compensated_steps) == 0

    @pytest.mark.asyncio
    async def test_create_saga_postgres_fail(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test create saga with PostgreSQL failure."""
        mock_postgres.create_document.side_effect = Exception("DB connection failed")

        coordinator._embedding_service = mock_embedding_service

        result = await coordinator.execute_create_saga(mock_document, mock_chunks)

        assert result.success is False
        assert "postgres_create" in result.error
        assert len(result.executed_steps) == 0
        assert len(result.compensated_steps) == 0

    @pytest.mark.asyncio
    async def test_create_saga_milvus_fail_compensates_postgres(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test create saga with Milvus failure triggers PostgreSQL compensation."""
        # PostgreSQL succeeds
        mock_postgres.create_document.return_value = mock_document
        mock_postgres.create_chunks.return_value = mock_chunks
        mock_postgres.delete_document.return_value = True

        # Milvus fails
        mock_milvus.insert_chunks.side_effect = Exception("Milvus connection failed")

        coordinator._embedding_service = mock_embedding_service
        mock_embedding_service.encode.return_value = MagicMock(
            dense=[[0.1] * 1024, [0.2] * 1024],
            sparse=[MagicMock(), MagicMock()],
        )

        result = await coordinator.execute_create_saga(mock_document, mock_chunks)

        assert result.success is False
        assert "milvus_create" in result.error
        assert "postgres_create" in result.executed_steps
        assert "postgres_create" in result.compensated_steps
        mock_postgres.delete_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_saga_neo4j_fail_compensates_milvus_postgres(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test create saga with Neo4j failure triggers Milvus and PostgreSQL compensation."""
        # PostgreSQL and Milvus succeed
        mock_postgres.create_document.return_value = mock_document
        mock_postgres.create_chunks.return_value = mock_chunks
        mock_postgres.delete_document.return_value = True
        mock_milvus.insert_chunks.return_value = ["chunk-0", "chunk-1"]
        mock_milvus.delete_by_doc_uuid.return_value = 2

        # Neo4j fails
        mock_neo4j.create_document_node.side_effect = Exception("Neo4j connection failed")

        coordinator._embedding_service = mock_embedding_service
        mock_embedding_service.encode.return_value = MagicMock(
            dense=[[0.1] * 1024, [0.2] * 1024],
            sparse=[MagicMock(), MagicMock()],
        )

        result = await coordinator.execute_create_saga(mock_document, mock_chunks)

        assert result.success is False
        assert "neo4j_create" in result.error
        assert "postgres_create" in result.executed_steps
        assert "milvus_create" in result.executed_steps
        assert "milvus_create" in result.compensated_steps
        assert "postgres_create" in result.compensated_steps

    @pytest.mark.asyncio
    async def test_create_saga_with_precomputed_embeddings(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
    ) -> None:
        """Test create saga with pre-computed embeddings."""
        mock_postgres.create_document.return_value = mock_document
        mock_postgres.create_chunks.return_value = mock_chunks
        mock_milvus.insert_chunks.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_document_node.return_value = "test-doc-uuid"
        mock_neo4j.create_chunk_nodes.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_contains_edges.return_value = 2

        embeddings = MagicMock(
            dense=[[0.1] * 1024, [0.2] * 1024],
            sparse=[MagicMock(), MagicMock()],
        )

        result = await coordinator.execute_create_saga(
            mock_document, mock_chunks, embeddings=embeddings
        )

        assert result.success is True


# =============================================================================
# Test Delete Saga
# =============================================================================


class TestDeleteSaga:
    """Tests for delete saga execution."""

    @pytest.mark.asyncio
    async def test_delete_saga_success(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test successful delete saga."""
        mock_neo4j.get_document_graph.return_value = {"nodes": [], "edges": []}
        mock_neo4j.delete_document_graph.return_value = 5
        mock_milvus.delete_by_doc_uuid.return_value = 3
        mock_postgres.get_document.return_value = MagicMock()
        mock_postgres.get_chunks_by_doc.return_value = []
        mock_postgres.delete_document.return_value = True

        result = await coordinator.execute_delete_saga("test-doc-uuid")

        assert result.success is True
        assert len(result.executed_steps) == 3
        assert "neo4j_delete" in result.executed_steps
        assert "milvus_delete" in result.executed_steps
        assert "postgres_delete" in result.executed_steps

    @pytest.mark.asyncio
    async def test_delete_saga_neo4j_fail(
        self,
        coordinator: SagaCoordinator,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test delete saga with Neo4j failure."""
        mock_neo4j.get_document_graph.side_effect = Exception("Neo4j error")

        result = await coordinator.execute_delete_saga("test-doc-uuid")

        assert result.success is False
        assert "neo4j_delete" in result.error
        assert len(result.compensated_steps) == 0

    @pytest.mark.asyncio
    async def test_delete_saga_milvus_fail_compensates(
        self,
        coordinator: SagaCoordinator,
        mock_neo4j: MagicMock,
        mock_milvus: MagicMock,
    ) -> None:
        """Test delete saga with Milvus failure triggers Neo4j compensation."""
        mock_neo4j.get_document_graph.return_value = {}
        mock_neo4j.delete_document_graph.return_value = 5
        mock_milvus.delete_by_doc_uuid.side_effect = Exception("Milvus error")

        result = await coordinator.execute_delete_saga("test-doc-uuid")

        assert result.success is False
        assert "milvus_delete" in result.error
        assert "neo4j_delete" in result.executed_steps
        assert "neo4j_delete" in result.compensated_steps


# =============================================================================
# Test Update Saga
# =============================================================================


class TestUpdateSaga:
    """Tests for update saga execution."""

    @pytest.mark.asyncio
    async def test_update_saga_success(
        self,
        coordinator: SagaCoordinator,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test successful update saga."""
        # Delete phase
        mock_neo4j.get_document_graph.return_value = {}
        mock_neo4j.delete_document_graph.return_value = 5
        mock_milvus.delete_by_doc_uuid.return_value = 3

        # Update phase
        mock_postgres.get_document.return_value = mock_document
        mock_postgres.get_chunks_by_doc.return_value = mock_chunks
        mock_postgres.update_document.return_value = mock_document
        mock_postgres.delete_chunks_by_doc.return_value = 2
        mock_postgres.create_chunks.return_value = mock_chunks

        # Create phase
        mock_milvus.insert_chunks.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_document_node.return_value = "test-doc-uuid"
        mock_neo4j.create_chunk_nodes.return_value = ["chunk-0", "chunk-1"]
        mock_neo4j.create_contains_edges.return_value = 2

        coordinator._embedding_service = mock_embedding_service
        mock_embedding_service.encode.return_value = MagicMock(
            dense=[[0.1] * 1024, [0.2] * 1024],
            sparse=[MagicMock(), MagicMock()],
        )

        result = await coordinator.execute_update_saga(
            "test-doc-uuid", mock_document, mock_chunks
        )

        assert result.success is True
        assert "neo4j_delete" in result.executed_steps
        assert "milvus_delete" in result.executed_steps
        assert "postgres_update" in result.executed_steps
        assert "milvus_create" in result.executed_steps
        assert "neo4j_create" in result.executed_steps


# =============================================================================
# Test Individual Steps
# =============================================================================


class TestPostgresCreateStep:
    """Tests for PostgresCreateStep."""

    @pytest.fixture
    def step(self, mock_postgres: MagicMock) -> PostgresCreateStep:
        """Create step instance."""
        return PostgresCreateStep(mock_postgres)

    @pytest.mark.asyncio
    async def test_execute_success(
        self,
        step: PostgresCreateStep,
        mock_postgres: MagicMock,
        mock_document: MagicMock,
        mock_chunks: list[MagicMock],
    ) -> None:
        """Test successful execution."""
        mock_postgres.create_document.return_value = mock_document
        mock_postgres.create_chunks.return_value = mock_chunks

        context = SagaContext(
            doc_uuid="test-uuid",
            document=mock_document,
            chunks=mock_chunks,
        )
        result = await step.execute(context)

        assert result.success is True
        assert result.step_name == "postgres_create"

    @pytest.mark.asyncio
    async def test_compensate_success(
        self,
        step: PostgresCreateStep,
        mock_postgres: MagicMock,
    ) -> None:
        """Test successful compensation."""
        mock_postgres.delete_document.return_value = True

        context = SagaContext(doc_uuid="test-uuid")
        result = await step.compensate(context)

        assert result.success is True


class TestMilvusCreateStep:
    """Tests for MilvusCreateStep."""

    @pytest.fixture
    def step(self, mock_milvus: MagicMock) -> MilvusCreateStep:
        """Create step instance."""
        return MilvusCreateStep(mock_milvus)

    @pytest.mark.asyncio
    async def test_execute_no_embeddings(
        self,
        step: MilvusCreateStep,
    ) -> None:
        """Test execution fails without embeddings."""
        context = SagaContext(doc_uuid="test-uuid")
        result = await step.execute(context)

        assert result.success is False
        assert "No embeddings" in result.error


class TestNeo4jCreateStep:
    """Tests for Neo4jCreateStep."""

    @pytest.fixture
    def step(self, mock_neo4j: MagicMock) -> Neo4jCreateStep:
        """Create step instance."""
        return Neo4jCreateStep(mock_neo4j)

    @pytest.mark.asyncio
    async def test_compensate_success(
        self,
        step: Neo4jCreateStep,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test successful compensation."""
        mock_neo4j.delete_document_graph.return_value = 5

        context = SagaContext(doc_uuid="test-uuid")
        result = await step.compensate(context)

        assert result.success is True


# =============================================================================
# Test Singleton Factory
# =============================================================================


class TestSingletonFactory:
    """Tests for singleton factory functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_saga_coordinator()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_saga_coordinator()

    def test_get_coordinator_creates_instance(
        self,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test get_saga_coordinator creates instance."""
        coordinator = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)

        assert coordinator is not None
        assert isinstance(coordinator, SagaCoordinator)

    def test_get_coordinator_returns_same_instance(
        self,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test get_saga_coordinator returns same instance."""
        coordinator1 = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)
        coordinator2 = get_saga_coordinator()

        assert coordinator1 is coordinator2

    def test_get_coordinator_requires_repos_first_call(self) -> None:
        """Test get_saga_coordinator requires repos on first call."""
        with pytest.raises(ValueError, match="All repositories required"):
            get_saga_coordinator()

    def test_close_coordinator(
        self,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test close_saga_coordinator clears singleton."""
        coordinator1 = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)

        close_saga_coordinator()

        coordinator2 = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)
        assert coordinator1 is not coordinator2

    def test_reset_coordinator(
        self,
        mock_postgres: MagicMock,
        mock_milvus: MagicMock,
        mock_neo4j: MagicMock,
    ) -> None:
        """Test reset_saga_coordinator creates new instance."""
        coordinator1 = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)

        reset_saga_coordinator()

        coordinator2 = get_saga_coordinator(mock_postgres, mock_milvus, mock_neo4j)
        assert coordinator1 is not coordinator2
