"""Tests for embedding service."""

import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from scipy.sparse import csr_array

from src.infrastructure.embedding.bge_m3 import (
    EmbeddingResult,
    EmbeddingService,
    close_embedding_service,
    get_embedding_service,
    reset_embedding_service,
)


class TestEmbeddingResult:
    """Tests for EmbeddingResult dataclass."""

    def test_empty_result(self) -> None:
        """Test empty result."""
        result = EmbeddingResult()
        assert len(result) == 0
        assert not result

    def test_result_with_data(self) -> None:
        """Test result with data."""
        dense = [[0.1] * 1024]
        sparse_dict = [{1: 0.5, 2: 0.3}]
        sparse = [csr_array(([0.5, 0.3], ([0, 0], [1, 2])), shape=(1, 30000))]

        result = EmbeddingResult(
            dense=dense,
            sparse=sparse,
            sparse_dict=sparse_dict,
        )

        assert len(result) == 1
        assert result
        assert len(result.dense[0]) == 1024

    def test_result_multiple_embeddings(self) -> None:
        """Test result with multiple embeddings."""
        dense = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        sparse_dict = [{1: 0.5}, {2: 0.3}, {3: 0.4}]
        sparse = [
            csr_array(([0.5], ([0], [1])), shape=(1, 30000)),
            csr_array(([0.3], ([0], [2])), shape=(1, 30000)),
            csr_array(([0.4], ([0], [3])), shape=(1, 30000)),
        ]

        result = EmbeddingResult(dense=dense, sparse=sparse, sparse_dict=sparse_dict)

        assert len(result) == 3


class TestEmbeddingServiceProperties:
    """Tests for EmbeddingService properties."""

    def test_dimension(self) -> None:
        """Test dimension property."""
        service = EmbeddingService()
        assert service.dimension == 1024

    def test_dimension_constant(self) -> None:
        """Test DIMENSION constant."""
        assert EmbeddingService.DIMENSION == 1024

    def test_vocab_size_constant(self) -> None:
        """Test VOCAB_SIZE constant."""
        assert EmbeddingService.VOCAB_SIZE == 30000

    def test_device_detection(self) -> None:
        """Test device detection returns valid value."""
        service = EmbeddingService()
        # Just check it returns one of the valid values
        assert service.device in ["cuda", "cpu"]

    def test_not_loaded_initially(self) -> None:
        """Test model not loaded initially."""
        service = EmbeddingService()
        assert not service.is_loaded

    def test_model_name(self) -> None:
        """Test model name property."""
        service = EmbeddingService(model_name="custom/model")
        assert service.model_name == "custom/model"

    def test_default_model_name(self) -> None:
        """Test default model name."""
        service = EmbeddingService()
        assert service.model_name == "BAAI/bge-m3"


class TestEmbeddingServiceEncode:
    """Tests for EmbeddingService encode methods."""

    @pytest.fixture
    def mock_model(self) -> MagicMock:
        """Create mock model."""
        mock = MagicMock()
        mock.encode.return_value = {
            "dense_vecs": np.array([[0.1] * 1024]),
            "lexical_weights": [{"test": 0.5, "hello": 0.3}],
        }
        mock.tokenizer.convert_tokens_to_ids.side_effect = lambda t: {
            "test": 123,
            "hello": 456,
        }.get(t, 0)
        mock.tokenizer.unk_token_id = 0
        return mock

    @pytest.fixture
    def mock_flag_embedding(self, mock_model: MagicMock) -> MagicMock:
        """Create mock FlagEmbedding module."""
        mock_module = MagicMock()
        mock_module.BGEM3FlagModel.return_value = mock_model
        return mock_module

    def test_encode_empty_list(self) -> None:
        """Test encode with empty list."""
        service = EmbeddingService()
        result = service.encode([])

        assert len(result) == 0
        assert not result

    def test_encode_calls_model(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode calls model correctly."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            result = service.encode(["test text"])

            assert len(result) == 1
            mock_model.encode.assert_called_once()
            call_kwargs = mock_model.encode.call_args[1]
            assert call_kwargs["return_dense"] is True
            assert call_kwargs["return_sparse"] is True
            assert call_kwargs["return_colbert_vecs"] is False

    def test_encode_returns_dense_embeddings(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode returns dense embeddings."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            result = service.encode(["test text"])

            assert len(result.dense) == 1
            assert len(result.dense[0]) == 1024

    def test_encode_returns_sparse_embeddings(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode returns sparse embeddings."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            result = service.encode(["test text"])

            assert len(result.sparse) == 1
            assert len(result.sparse_dict) == 1
            assert 123 in result.sparse_dict[0]  # "test" token id
            assert 456 in result.sparse_dict[0]  # "hello" token id

    def test_encode_with_custom_batch_size(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode with custom batch size."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            service.encode(["test text"], batch_size=8)

            call_kwargs = mock_model.encode.call_args[1]
            assert call_kwargs["batch_size"] == 8

    def test_encode_uses_default_batch_size(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode uses default batch size."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService(batch_size=16)
            service.encode(["test text"])

            call_kwargs = mock_model.encode.call_args[1]
            assert call_kwargs["batch_size"] == 16

    def test_encode_query(
        self, mock_model: MagicMock, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode_query method."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            result = service.encode_query("test query")

            assert len(result) == 1
            mock_model.encode.assert_called_once_with(
                ["test query"],
                batch_size=12,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )

    def test_encode_documents(
        self, mock_flag_embedding: MagicMock
    ) -> None:
        """Test encode_documents method."""
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": np.array([[0.1] * 1024, [0.2] * 1024]),
            "lexical_weights": [{"test": 0.5}, {"hello": 0.3}],
        }
        mock_model.tokenizer.convert_tokens_to_ids.side_effect = lambda t: {
            "test": 123,
            "hello": 456,
        }.get(t, 0)
        mock_model.tokenizer.unk_token_id = 0
        mock_flag_embedding.BGEM3FlagModel.return_value = mock_model

        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            result = service.encode_documents(["doc1", "doc2"])

            assert len(result) == 2


class TestEmbeddingServiceModelLoading:
    """Tests for model loading and unloading."""

    @pytest.fixture
    def mock_flag_embedding(self) -> MagicMock:
        """Create mock FlagEmbedding module."""
        mock_model = MagicMock()
        mock_module = MagicMock()
        mock_module.BGEM3FlagModel.return_value = mock_model
        return mock_module

    def test_lazy_loading(self) -> None:
        """Test model is not loaded until needed."""
        service = EmbeddingService()
        assert service._model is None

    def test_load_model_sets_model(self, mock_flag_embedding: MagicMock) -> None:
        """Test _load_model sets the model."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            service._load_model()

            assert service._model is not None
            assert service.is_loaded

    def test_load_model_called_once(self, mock_flag_embedding: MagicMock) -> None:
        """Test _load_model only loads once."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            service._load_model()
            service._load_model()

            mock_flag_embedding.BGEM3FlagModel.assert_called_once()

    def test_load_model_import_error(self) -> None:
        """Test _load_model raises ImportError if FlagEmbedding not installed."""
        # Remove FlagEmbedding from sys.modules if it exists
        original = sys.modules.get("FlagEmbedding")
        try:
            if "FlagEmbedding" in sys.modules:
                del sys.modules["FlagEmbedding"]

            with patch.dict(sys.modules, {"FlagEmbedding": None}):
                service = EmbeddingService()

                with pytest.raises(ImportError) as exc_info:
                    service._load_model()

                assert "FlagEmbedding is required" in str(exc_info.value)
        finally:
            if original is not None:
                sys.modules["FlagEmbedding"] = original

    def test_unload_clears_model(self, mock_flag_embedding: MagicMock) -> None:
        """Test unload clears the model."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            service = EmbeddingService()
            service._load_model()
            assert service.is_loaded

            service.unload()

            assert not service.is_loaded
            assert service._model is None

    def test_context_manager(self, mock_flag_embedding: MagicMock) -> None:
        """Test context manager unloads model."""
        with patch.dict(sys.modules, {"FlagEmbedding": mock_flag_embedding}):
            with EmbeddingService() as service:
                service._load_model()
                assert service.is_loaded

            assert not service.is_loaded


class TestSparseVectorConversion:
    """Tests for sparse vector format conversion."""

    @pytest.fixture
    def service_with_mock_model(self) -> EmbeddingService:
        """Create service with mock model."""
        mock_model = MagicMock()
        mock_model.tokenizer.convert_tokens_to_ids.side_effect = lambda t: {
            "hello": 100,
            "world": 200,
            "test": 300,
        }.get(t, 0)
        mock_model.tokenizer.unk_token_id = 0

        service = EmbeddingService()
        service._model = mock_model
        return service

    def test_convert_sparse_to_milvus_format(
        self, service_with_mock_model: EmbeddingService
    ) -> None:
        """Test sparse vector conversion."""
        lexical_weights = [{"hello": 0.5, "world": 0.3}]

        dict_result, csr_result = service_with_mock_model._convert_sparse_to_milvus_format(
            lexical_weights
        )

        assert len(dict_result) == 1
        assert 100 in dict_result[0]  # hello
        assert 200 in dict_result[0]  # world
        assert dict_result[0][100] == 0.5
        assert dict_result[0][200] == 0.3

        assert len(csr_result) == 1
        assert isinstance(csr_result[0], csr_array)

    def test_convert_sparse_filters_unknown_tokens(
        self, service_with_mock_model: EmbeddingService
    ) -> None:
        """Test that unknown tokens are filtered out."""
        lexical_weights = [{"hello": 0.5, "unknown_token": 0.3}]

        dict_result, _ = service_with_mock_model._convert_sparse_to_milvus_format(
            lexical_weights
        )

        assert 100 in dict_result[0]  # hello
        assert 0 not in dict_result[0]  # unknown_token converted to 0 (unk_token_id)

    def test_convert_sparse_empty_weights(
        self, service_with_mock_model: EmbeddingService
    ) -> None:
        """Test conversion with empty weights."""
        lexical_weights = [{}]

        dict_result, csr_result = service_with_mock_model._convert_sparse_to_milvus_format(
            lexical_weights
        )

        assert dict_result[0] == {}
        assert csr_result[0].nnz == 0  # No non-zero elements


class TestSingleton:
    """Tests for singleton factory functions."""

    def test_get_embedding_service_creates_instance(self) -> None:
        """Test get_embedding_service creates instance."""
        reset_embedding_service()

        service = get_embedding_service()

        assert service is not None
        assert isinstance(service, EmbeddingService)

    def test_get_embedding_service_returns_same_instance(self) -> None:
        """Test get_embedding_service returns same instance."""
        reset_embedding_service()

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

    def test_get_embedding_service_custom_params(self) -> None:
        """Test get_embedding_service with custom parameters."""
        reset_embedding_service()

        service = get_embedding_service(
            model_name="custom/model",
            use_fp16=False,
            batch_size=8,
        )

        assert service.model_name == "custom/model"

    def test_close_embedding_service(self) -> None:
        """Test close_embedding_service."""
        reset_embedding_service()

        service1 = get_embedding_service()

        close_embedding_service()

        # After close, getting service again creates a new instance
        service2 = get_embedding_service()
        assert service1 is not service2

    def test_reset_embedding_service(self) -> None:
        """Test reset_embedding_service creates new instance."""
        reset_embedding_service()
        service1 = get_embedding_service()

        reset_embedding_service()
        service2 = get_embedding_service()

        assert service1 is not service2
