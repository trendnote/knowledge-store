"""Tests for Neo4j repository."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.graph import ChunkNode, DocumentNode, Entity, GraphSearchResult
from src.repositories.neo4j.repository import (
    Neo4jRepository,
    get_neo4j_repository,
    reset_neo4j_repository,
)


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


@pytest.fixture
def sample_document() -> DocumentNode:
    """Sample document node."""
    return DocumentNode(
        doc_uuid="doc-001",
        title="Test Document",
        source="wiki",
        security_level="internal",
    )


@pytest.fixture
def sample_chunks() -> list[ChunkNode]:
    """Sample chunk nodes."""
    return [
        ChunkNode(
            chunk_uuid="chunk-001",
            doc_uuid="doc-001",
            sequence=0,
            text_preview="This is the first chunk of the document.",
            section_path="/intro",
        ),
        ChunkNode(
            chunk_uuid="chunk-002",
            doc_uuid="doc-001",
            sequence=1,
            text_preview="This is the second chunk with more content.",
            section_path="/body",
        ),
    ]


class TestDocumentNodeCRUD:
    """Tests for document node operations."""

    async def test_create_document_node(
        self, repo: Neo4jRepository, mock_client: MagicMock, sample_document: DocumentNode
    ) -> None:
        """Test document node creation."""
        mock_client.execute_write.return_value = [{"doc_uuid": "doc-001"}]

        result = await repo.create_document_node(sample_document)

        assert result == "doc-001"
        mock_client.execute_write.assert_called_once()
        call_args = mock_client.execute_write.call_args
        assert "MERGE" in call_args[0][0]
        assert call_args[0][1]["doc_uuid"] == "doc-001"

    async def test_create_document_node_returns_uuid_on_empty_result(
        self, repo: Neo4jRepository, mock_client: MagicMock, sample_document: DocumentNode
    ) -> None:
        """Test document creation returns input UUID when result is empty."""
        mock_client.execute_write.return_value = []

        result = await repo.create_document_node(sample_document)

        assert result == "doc-001"

    async def test_get_document_node_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting existing document node."""
        mock_client.execute_read.return_value = [
            {"doc": {"doc_uuid": "doc-001", "title": "Test", "source": "wiki"}}
        ]

        result = await repo.get_document_node("doc-001")

        assert result is not None
        assert result["doc_uuid"] == "doc-001"
        assert result["title"] == "Test"

    async def test_get_document_node_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting non-existent document node."""
        mock_client.execute_read.return_value = []

        result = await repo.get_document_node("nonexistent")

        assert result is None

    async def test_update_document_node(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test updating document node properties."""
        mock_client.execute_write.return_value = [{"doc_uuid": "doc-001"}]

        result = await repo.update_document_node(
            "doc-001", {"title": "Updated Title", "status": "published"}
        )

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "SET" in call_args[0][0]
        assert "title" in call_args[0][0]
        assert "status" in call_args[0][0]

    async def test_update_document_node_empty_updates(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test updating with empty updates returns True."""
        result = await repo.update_document_node("doc-001", {})

        assert result is True
        mock_client.execute_write.assert_not_called()

    async def test_update_document_node_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test updating non-existent document returns False."""
        mock_client.execute_write.return_value = []

        result = await repo.update_document_node("nonexistent", {"title": "New"})

        assert result is False

    async def test_delete_document_graph(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test document graph deletion."""
        mock_client.execute_write.return_value = [{"deleted_count": 5}]

        result = await repo.delete_document_graph("doc-001")

        assert result == 5
        call_args = mock_client.execute_write.call_args
        assert "DETACH DELETE" in call_args[0][0]

    async def test_delete_document_graph_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting non-existent document returns 0."""
        mock_client.execute_write.return_value = []

        result = await repo.delete_document_graph("nonexistent")

        assert result == 0

    async def test_document_exists_true(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test document exists check - found."""
        mock_client.execute_read.return_value = [{"exists": True}]

        result = await repo.document_exists("doc-001")

        assert result is True

    async def test_document_exists_false(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test document exists check - not found."""
        mock_client.execute_read.return_value = [{"exists": False}]

        result = await repo.document_exists("nonexistent")

        assert result is False

    async def test_list_documents(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test listing documents."""
        mock_client.execute_read.return_value = [
            {"doc": {"doc_uuid": "doc-001", "title": "Doc 1"}},
            {"doc": {"doc_uuid": "doc-002", "title": "Doc 2"}},
        ]

        result = await repo.list_documents(limit=10)

        assert len(result) == 2
        assert result[0]["doc_uuid"] == "doc-001"

    async def test_list_documents_with_filters(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test listing documents with filters."""
        mock_client.execute_read.return_value = []

        await repo.list_documents(source="wiki", security_level="internal")

        call_args = mock_client.execute_read.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "source" in params
        assert "security_level" in params
        assert "WHERE" in query


class TestChunkNodeCRUD:
    """Tests for chunk node operations."""

    async def test_create_chunk_nodes_batch(
        self, repo: Neo4jRepository, mock_client: MagicMock, sample_chunks: list[ChunkNode]
    ) -> None:
        """Test batch chunk creation."""
        mock_client.execute_write.return_value = [
            {"chunk_uuid": "chunk-001"},
            {"chunk_uuid": "chunk-002"},
        ]

        result = await repo.create_chunk_nodes(sample_chunks)

        assert len(result) == 2
        assert "chunk-001" in result
        assert "chunk-002" in result
        mock_client.execute_write.assert_called_once()
        call_args = mock_client.execute_write.call_args
        assert "UNWIND" in call_args[0][0]

    async def test_create_chunk_nodes_empty_list(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating empty chunk list."""
        result = await repo.create_chunk_nodes([])

        assert result == []
        mock_client.execute_write.assert_not_called()

    async def test_create_chunk_nodes_truncates_text(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test that long text_preview is truncated."""
        long_text = "x" * 1000
        chunk = ChunkNode(
            chunk_uuid="chunk-001",
            doc_uuid="doc-001",
            sequence=0,
            text_preview=long_text,
        )
        mock_client.execute_write.return_value = [{"chunk_uuid": "chunk-001"}]

        await repo.create_chunk_nodes([chunk])

        call_args = mock_client.execute_write.call_args
        chunks_data = call_args[0][1]["chunks"]
        assert len(chunks_data[0]["text_preview"]) == 500

    async def test_get_chunk_node_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting existing chunk node."""
        mock_client.execute_read.return_value = [
            {"chunk": {"chunk_uuid": "chunk-001", "text_preview": "Test"}}
        ]

        result = await repo.get_chunk_node("chunk-001")

        assert result is not None
        assert result["chunk_uuid"] == "chunk-001"

    async def test_get_chunk_node_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting non-existent chunk node."""
        mock_client.execute_read.return_value = []

        result = await repo.get_chunk_node("nonexistent")

        assert result is None

    async def test_get_chunks_by_doc(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting chunks for a document."""
        mock_client.execute_read.return_value = [
            {"chunk": {"chunk_uuid": "chunk-001", "sequence": 0}},
            {"chunk": {"chunk_uuid": "chunk-002", "sequence": 1}},
        ]

        result = await repo.get_chunks_by_doc("doc-001")

        assert len(result) == 2
        call_args = mock_client.execute_read.call_args
        assert "CONTAINS" in call_args[0][0]
        assert "ORDER BY c.sequence" in call_args[0][0]

    async def test_delete_chunks_by_doc(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test deleting chunks for a document."""
        mock_client.execute_write.return_value = [{"deleted_count": 5}]

        result = await repo.delete_chunks_by_doc("doc-001")

        assert result == 5


class TestRelationships:
    """Tests for relationship operations."""

    async def test_create_contains_edges(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating CONTAINS edges."""
        mock_client.execute_write.return_value = [{"created": 2}]

        result = await repo.create_contains_edges(
            "doc-001", ["chunk-001", "chunk-002"]
        )

        assert result == 2
        call_args = mock_client.execute_write.call_args
        assert "CONTAINS" in call_args[0][0]
        assert "MERGE" in call_args[0][0]

    async def test_create_contains_edges_empty_list(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating CONTAINS with empty chunk list."""
        result = await repo.create_contains_edges("doc-001", [])

        assert result == 0
        mock_client.execute_write.assert_not_called()

    async def test_create_wrote_edge(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating WROTE edge."""
        mock_client.execute_write.return_value = [{"rel_type": "WROTE"}]

        result = await repo.create_wrote_edge("emp-001", "doc-001")

        assert result is True
        call_args = mock_client.execute_write.call_args
        assert "WROTE" in call_args[0][0]

    async def test_create_wrote_edge_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating WROTE edge when nodes don't exist."""
        mock_client.execute_write.return_value = []

        result = await repo.create_wrote_edge("emp-001", "doc-001")

        assert result is False

    async def test_create_mentions_edges_person(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating MENTIONS edges for Person entities."""
        mock_client.execute_write.return_value = [{"created": 2}]
        entities = [
            Entity(entity_type="Person", entity_id="emp-001", name="John", confidence=0.9),
            Entity(entity_type="Person", entity_id="emp-002", name="Jane", confidence=0.8),
        ]

        result = await repo.create_mentions_edges("chunk-001", entities)

        assert result == 2
        call_args = mock_client.execute_write.call_args
        assert "MENTIONS" in call_args[0][0]
        assert "Person" in call_args[0][0]

    async def test_create_mentions_edges_organization(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating MENTIONS edges for Organization entities."""
        mock_client.execute_write.return_value = [{"created": 1}]
        entities = [
            Entity(entity_type="Organization", entity_id="org-001", name="Acme", confidence=0.95),
        ]

        result = await repo.create_mentions_edges("chunk-001", entities)

        assert result == 1

    async def test_create_mentions_edges_mixed(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating MENTIONS edges with mixed entity types."""
        mock_client.execute_write.side_effect = [[{"created": 1}], [{"created": 1}]]
        entities = [
            Entity(entity_type="Person", entity_id="emp-001", name="John", confidence=0.9),
            Entity(entity_type="Organization", entity_id="org-001", name="Acme", confidence=0.8),
        ]

        result = await repo.create_mentions_edges("chunk-001", entities)

        assert result == 2

    async def test_create_mentions_edges_empty(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test creating MENTIONS with empty entity list."""
        result = await repo.create_mentions_edges("chunk-001", [])

        assert result == 0
        mock_client.execute_write.assert_not_called()

    async def test_get_document_author(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting document author."""
        mock_client.execute_read.return_value = [
            {"person": {"emp_id": "emp-001", "name": "John"}}
        ]

        result = await repo.get_document_author("doc-001")

        assert result is not None
        assert result["emp_id"] == "emp-001"

    async def test_get_chunk_mentions(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting entities mentioned in chunk."""
        mock_client.execute_read.return_value = [
            {"entity_type": "Person", "entity": {"emp_id": "emp-001"}, "confidence": 0.9},
        ]

        result = await repo.get_chunk_mentions("chunk-001")

        assert len(result) == 1
        assert result[0]["entity_type"] == "Person"


class TestGraphSearch:
    """Tests for graph search operations."""

    async def test_graph_search(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test basic graph search."""
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

        results = await repo.graph_search("test", top_k=10)

        assert len(results) == 1
        assert isinstance(results[0], GraphSearchResult)
        assert results[0].chunk_uuid == "chunk-001"
        call_args = mock_client.execute_read.call_args
        assert "CONTAINS" in call_args[0][0]

    async def test_graph_search_with_acl_filter(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test graph search with ACL filter."""
        mock_client.execute_read.return_value = []

        await repo.graph_search("test", doc_uuids=["doc-001", "doc-002"])

        call_args = mock_client.execute_read.call_args
        query = call_args[0][0]
        params = call_args[0][1]

        assert "doc_uuids" in params
        assert "IN $doc_uuids" in query

    async def test_graph_search_empty_acl(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test graph search with empty ACL returns empty."""
        results = await repo.graph_search("test", doc_uuids=[])

        assert results == []
        mock_client.execute_read.assert_not_called()

    async def test_graph_search_case_insensitive(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test graph search is case insensitive."""
        mock_client.execute_read.return_value = []

        await repo.graph_search("TEST")

        call_args = mock_client.execute_read.call_args
        params = call_args[0][1]
        assert params["query"] == "test"  # Should be lowercased

    async def test_graph_search_with_context(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test graph search with entity context."""
        mock_client.execute_read.return_value = [
            {
                "chunk_uuid": "chunk-001",
                "doc_uuid": "doc-001",
                "title": "Test Doc",
                "text_preview": "Content about John",
                "section_path": "/intro",
                "score": 1.0,
                "related_entities": ["John", "Acme Corp"],
            }
        ]

        results = await repo.graph_search_with_context("test", top_k=10)

        assert len(results) == 1
        assert "John" in results[0].related_entities

    async def test_graph_search_with_context_empty_acl(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test graph search with context returns empty for empty ACL."""
        results = await repo.graph_search_with_context("test", doc_uuids=[])

        assert results == []

    async def test_find_related_documents(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test finding related documents."""
        mock_client.execute_read.return_value = [
            {
                "doc_uuid": "doc-002",
                "title": "Related Doc",
                "shared_entities": ["John", "Project X"],
                "relevance_score": 5,
            }
        ]

        results = await repo.find_related_documents("doc-001", limit=10)

        assert len(results) == 1
        assert results[0]["doc_uuid"] == "doc-002"
        call_args = mock_client.execute_read.call_args
        assert "MENTIONS" in call_args[0][0]

    async def test_get_document_graph(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting full document graph."""
        # Mock get_document_node
        mock_client.execute_read.side_effect = [
            [{"doc": {"doc_uuid": "doc-001", "title": "Test"}}],  # get_document_node
            [  # chunks query
                {
                    "chunk": {"chunk_uuid": "chunk-001", "sequence": 0},
                    "mentions": [{"type": "Person", "name": "John"}],
                }
            ],
            [],  # get_document_author
        ]

        result = await repo.get_document_graph("doc-001")

        assert result["document"] is not None
        assert len(result["chunks"]) == 1
        assert result["chunks"][0]["mentions"] == [{"type": "Person", "name": "John"}]

    async def test_get_document_graph_not_found(
        self, repo: Neo4jRepository, mock_client: MagicMock
    ) -> None:
        """Test getting graph for non-existent document."""
        mock_client.execute_read.return_value = []

        result = await repo.get_document_graph("nonexistent")

        assert result["document"] is None
        assert result["chunks"] == []


class TestGraphSearchResult:
    """Tests for GraphSearchResult model."""

    def test_from_record(self) -> None:
        """Test creating GraphSearchResult from record."""
        record = {
            "chunk_uuid": "chunk-001",
            "doc_uuid": "doc-001",
            "title": "Test Document",
            "text_preview": "Test content",
            "section_path": "/intro",
            "score": 0.95,
            "path_length": 2,
            "related_entities": ["John", "Acme"],
        }

        result = GraphSearchResult.from_record(record)

        assert result.chunk_uuid == "chunk-001"
        assert result.doc_uuid == "doc-001"
        assert result.title == "Test Document"
        assert result.score == 0.95
        assert result.path_length == 2
        assert len(result.related_entities) == 2

    def test_from_record_missing_fields(self) -> None:
        """Test creating GraphSearchResult with missing fields."""
        record = {"chunk_uuid": "chunk-001", "score": 0.5}

        result = GraphSearchResult.from_record(record)

        assert result.chunk_uuid == "chunk-001"
        assert result.doc_uuid == ""
        assert result.title == ""
        assert result.section_path is None
        assert result.path_length == 0
        assert result.related_entities == []


class TestSingleton:
    """Tests for singleton factory."""

    def test_get_neo4j_repository_creates_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test that factory creates repository instance."""
        reset_neo4j_repository()

        repo = get_neo4j_repository(mock_client)

        assert repo is not None
        assert isinstance(repo, Neo4jRepository)

    def test_get_neo4j_repository_returns_same_instance(
        self, mock_client: MagicMock
    ) -> None:
        """Test that factory returns same instance."""
        reset_neo4j_repository()

        repo1 = get_neo4j_repository(mock_client)
        repo2 = get_neo4j_repository()

        assert repo1 is repo2

    def test_reset_neo4j_repository(self, mock_client: MagicMock) -> None:
        """Test resetting singleton."""
        reset_neo4j_repository()
        repo1 = get_neo4j_repository(mock_client)

        reset_neo4j_repository()
        repo2 = get_neo4j_repository(mock_client)

        assert repo1 is not repo2

    def test_get_neo4j_repository_auto_creates_client(self) -> None:
        """Test that factory auto-creates client when not provided."""
        reset_neo4j_repository()

        with patch(
            "src.infrastructure.database.get_neo4j_client"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            repo = get_neo4j_repository()

            assert repo is not None
            mock_get_client.assert_called_once()
