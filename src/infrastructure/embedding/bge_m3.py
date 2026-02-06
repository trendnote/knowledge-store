"""BGE-M3 embedding service for dense and sparse embeddings.

This module provides a service for generating embeddings using the BGE-M3 model:
- Dense embeddings (1024 dimensions)
- Sparse embeddings (lexical weights)
- Batch processing support
- CPU/GPU auto-detection

Example:
    >>> from src.infrastructure.embedding import get_embedding_service
    >>> service = get_embedding_service()
    >>> result = service.encode(["Hello, world!", "Another text"])
    >>> print(len(result.dense[0]))  # 1024
    >>> print(result.sparse[0])  # {token_id: weight, ...}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np
from scipy.sparse import csr_array

if TYPE_CHECKING:
    from FlagEmbedding import BGEM3FlagModel


@dataclass
class EmbeddingResult:
    """Result of embedding generation.

    Attributes:
        dense: List of dense embeddings (1024 dimensions each)
        sparse: List of sparse embeddings as scipy csr_array for Milvus
        sparse_dict: List of sparse embeddings as dict[int, float]
    """

    dense: list[list[float]] = field(default_factory=list)
    sparse: list[csr_array] = field(default_factory=list)
    sparse_dict: list[dict[int, float]] = field(default_factory=list)

    def __len__(self) -> int:
        """Return number of embeddings."""
        return len(self.dense)

    def __bool__(self) -> bool:
        """Return True if embeddings exist."""
        return len(self.dense) > 0


class EmbeddingService:
    """Service for generating dense and sparse embeddings using BGE-M3.

    This service provides:
    - Lazy model loading (loaded on first use)
    - Dense + Sparse embeddings in one call
    - Batch processing with configurable batch size
    - CPU/GPU auto-detection
    - Context manager support for memory cleanup

    Example:
        >>> service = EmbeddingService()
        >>> result = service.encode(["Hello, world!"])
        >>> print(service.dimension)  # 1024
        >>> service.unload()  # Free memory
    """

    DIMENSION = 1024  # BGE-M3 dense embedding dimension
    VOCAB_SIZE = 30000  # Approximate vocabulary size for sparse vectors

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        use_fp16: bool = True,
        batch_size: int = 12,
    ) -> None:
        """Initialize embedding service.

        Args:
            model_name: HuggingFace model name or local path
            use_fp16: Use FP16 for memory efficiency
            batch_size: Default batch size for encoding
        """
        self._model_name = model_name
        self._use_fp16 = use_fp16
        self._batch_size = batch_size
        self._model: BGEM3FlagModel | None = None

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self.DIMENSION

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model is not None

    @property
    def device(self) -> str:
        """Return device (cuda or cpu)."""
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    @property
    def model_name(self) -> str:
        """Return model name."""
        return self._model_name

    def _load_model(self) -> None:
        """Load model lazily on first use.

        Raises:
            ImportError: If FlagEmbedding is not installed
        """
        if self._model is not None:
            return

        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as e:
            raise ImportError(
                "FlagEmbedding is required. Install with: pip install FlagEmbedding"
            ) from e

        self._model = BGEM3FlagModel(
            self._model_name,
            use_fp16=self._use_fp16,
            device=self.device,
        )

    def unload(self) -> None:
        """Unload model from memory."""
        if self._model is not None:
            del self._model
            self._model = None
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def __enter__(self) -> EmbeddingService:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - unload model."""
        self.unload()

    def _convert_sparse_to_milvus_format(
        self,
        lexical_weights: list[dict[str, float]],
    ) -> tuple[list[dict[int, float]], list[csr_array]]:
        """Convert BGE-M3 sparse output to Milvus format.

        BGE-M3 outputs: dict[str, float] (token -> weight)
        Milvus expects: scipy.sparse.csr_array for SPARSE_FLOAT_VECTOR

        Args:
            lexical_weights: List of token-weight dictionaries

        Returns:
            Tuple of (dict format, csr_array format)
        """
        assert self._model is not None

        tokenizer = self._model.tokenizer
        dict_results: list[dict[int, float]] = []
        csr_results: list[csr_array] = []

        for weights in lexical_weights:
            converted: dict[int, float] = {}
            indices: list[int] = []
            values: list[float] = []

            for token, weight in weights.items():
                # Convert token to ID
                token_id = tokenizer.convert_tokens_to_ids(token)
                if isinstance(token_id, int) and token_id != tokenizer.unk_token_id:
                    converted[token_id] = float(weight)
                    indices.append(token_id)
                    values.append(float(weight))

            dict_results.append(converted)

            # Create CSR array for Milvus
            if indices:
                row_indices = [0] * len(indices)
                sparse = csr_array(
                    (values, (row_indices, indices)),
                    shape=(1, self.VOCAB_SIZE),
                )
                csr_results.append(sparse)
            else:
                # Empty sparse vector
                csr_results.append(csr_array((1, self.VOCAB_SIZE)))

        return dict_results, csr_results

    def encode(
        self,
        texts: list[str],
        batch_size: int | None = None,
    ) -> EmbeddingResult:
        """Generate dense and sparse embeddings.

        Args:
            texts: List of texts to encode
            batch_size: Batch size (uses default if not specified)

        Returns:
            EmbeddingResult with dense and sparse embeddings
        """
        if not texts:
            return EmbeddingResult()

        self._load_model()
        assert self._model is not None

        batch_size = batch_size or self._batch_size

        output = self._model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        # Convert numpy arrays to lists
        dense_vecs = output["dense_vecs"]
        dense = dense_vecs.tolist() if isinstance(dense_vecs, np.ndarray) else list(dense_vecs)

        # Convert sparse format for Milvus
        sparse_dict, sparse_csr = self._convert_sparse_to_milvus_format(
            output["lexical_weights"]
        )

        return EmbeddingResult(dense=dense, sparse=sparse_csr, sparse_dict=sparse_dict)

    def encode_query(self, query: str) -> EmbeddingResult:
        """Encode a single query.

        Convenience method for encoding a single text.

        Args:
            query: Query text

        Returns:
            EmbeddingResult with single embedding
        """
        return self.encode([query])

    def encode_documents(
        self,
        documents: list[str],
        batch_size: int | None = None,
    ) -> EmbeddingResult:
        """Encode multiple documents.

        Same as encode() but with explicit naming for clarity.

        Args:
            documents: List of document texts
            batch_size: Batch size

        Returns:
            EmbeddingResult with document embeddings
        """
        return self.encode(documents, batch_size)


# =============================================================================
# Singleton Factory
# =============================================================================

_service: EmbeddingService | None = None


def get_embedding_service(
    model_name: str = "BAAI/bge-m3",
    use_fp16: bool = True,
    batch_size: int = 12,
) -> EmbeddingService:
    """Get or create embedding service singleton.

    Args:
        model_name: Model name (only used on first call)
        use_fp16: Use FP16 (only used on first call)
        batch_size: Batch size (only used on first call)

    Returns:
        EmbeddingService singleton instance
    """
    global _service
    if _service is None:
        _service = EmbeddingService(
            model_name=model_name,
            use_fp16=use_fp16,
            batch_size=batch_size,
        )
    return _service


def close_embedding_service() -> None:
    """Close and unload the embedding service singleton."""
    global _service
    if _service is not None:
        _service.unload()
        _service = None


def reset_embedding_service() -> None:
    """Reset the embedding service singleton (for testing)."""
    global _service
    _service = None
