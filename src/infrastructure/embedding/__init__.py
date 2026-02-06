"""Embedding infrastructure module.

This module provides embedding services:
- EmbeddingService: BGE-M3 based embedding generation
- EmbeddingResult: Dense + Sparse embedding result
"""

from src.infrastructure.embedding.bge_m3 import (
    EmbeddingResult,
    EmbeddingService,
    close_embedding_service,
    get_embedding_service,
    reset_embedding_service,
)

__all__ = [
    "EmbeddingResult",
    "EmbeddingService",
    "close_embedding_service",
    "get_embedding_service",
    "reset_embedding_service",
]
