# Task Execution Plan: 2.3.1 - Embedding Service 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.3.1 |
| **Task Name** | Embedding Service 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.1.1 |

### Description
BGE-M3 모델을 사용하여 Dense + Sparse 임베딩을 생성하는 서비스를 구현합니다.

### Acceptance Criteria
- [ ] `src/infrastructure/embedding/bge_m3.py` 생성
- [ ] BGE-M3 모델 로드 (lazy loading)
- [ ] Dense + Sparse 임베딩 동시 생성
- [ ] Batch 처리 지원
- [ ] CPU/GPU 자동 감지

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.4 Infrastructure Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.4 Embedding Model

### 2.2 BGE-M3 모델 특성
```python
from FlagEmbedding import BGEM3FlagModel

# 모델 로드
model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

# 임베딩 생성 (Dense + Sparse 동시)
output = model.encode(
    texts,
    batch_size=12,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=False  # ColBERT 불필요
)
# output['dense_vecs']: (N, 1024) 배열
# output['lexical_weights']: list[dict[str, float]]
```

### 2.3 설계 결정
1. **Lazy Loading**: 첫 호출 시에만 모델 로드 (메모리 효율)
2. **Singleton Pattern**: 전역 인스턴스로 중복 로드 방지
3. **Batch Processing**: batch_size=12 (GPU 메모리 고려)
4. **FP16**: 메모리 절약 및 추론 속도 향상
5. **CPU/GPU 자동 감지**: torch.cuda.is_available() 활용

### 2.4 클래스 구조
```
EmbeddingService
├── __init__(model_name, use_fp16, batch_size)
├── _load_model() -> None (lazy load)
├── encode(texts) -> EmbeddingResult
├── encode_batch(texts, batch_size) -> EmbeddingResult
└── dimension -> int (1024)

EmbeddingResult
├── dense: list[list[float]]
├── sparse: list[dict[int, float]]
└── __len__() -> int
```

### 2.5 Sparse Vector 포맷
Milvus SPARSE_FLOAT_VECTOR는 `dict[int, float]` 형식을 기대:
```python
# BGE-M3 출력: dict[str, float] (token -> weight)
{"the": 0.5, "embedding": 0.8}

# Milvus 요구: dict[int, float] (token_id -> weight)
# 변환 필요: tokenizer.convert_tokens_to_ids() 사용
```

---

## 3. Implementation Steps

### Step 1: 기본 클래스 및 결과 모델 정의 (0.5h)

**작업 내용:**
1. EmbeddingResult 데이터 클래스 정의
2. EmbeddingService 클래스 기본 구조
3. 설정 인터페이스 정의

**src/infrastructure/embedding/bge_m3.py:**
```python
"""BGE-M3 embedding service for dense and sparse embeddings."""
from dataclasses import dataclass, field
from typing import Any

import torch


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""

    dense: list[list[float]] = field(default_factory=list)
    sparse: list[dict[int, float]] = field(default_factory=list)

    def __len__(self) -> int:
        """Return number of embeddings."""
        return len(self.dense)

    def __bool__(self) -> bool:
        """Return True if embeddings exist."""
        return len(self.dense) > 0


class EmbeddingService:
    """Service for generating dense and sparse embeddings using BGE-M3."""

    DIMENSION = 1024  # BGE-M3 dense embedding dimension

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
        self._model: Any = None

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
        return "cuda" if torch.cuda.is_available() else "cpu"
```

**완료 기준:**
- [ ] EmbeddingResult 클래스 정의
- [ ] EmbeddingService 기본 구조 완성
- [ ] device 속성 구현

---

### Step 2: 모델 로드 및 언로드 (1h)

**작업 내용:**
1. lazy loading 구현
2. 모델 언로드 메서드
3. GPU/CPU 자동 감지

**src/infrastructure/embedding/bge_m3.py (계속):**
```python
    def _load_model(self) -> None:
        """Load model lazily on first use."""
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
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def __enter__(self) -> "EmbeddingService":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - unload model."""
        self.unload()
```

**완료 기준:**
- [ ] _load_model lazy loading 구현
- [ ] unload 메서드 구현
- [ ] GPU 캐시 정리 구현
- [ ] context manager 지원

---

### Step 3: 임베딩 생성 메서드 (1.5h)

**작업 내용:**
1. encode 메서드 (단일/배치)
2. Sparse vector 포맷 변환
3. 에러 핸들링

**src/infrastructure/embedding/bge_m3.py (계속):**
```python
    def _convert_sparse_to_milvus_format(
        self,
        lexical_weights: list[dict[str, float]],
    ) -> list[dict[int, float]]:
        """Convert BGE-M3 sparse output to Milvus format.

        BGE-M3 outputs: dict[str, float] (token -> weight)
        Milvus expects: dict[int, float] (token_id -> weight)

        Args:
            lexical_weights: List of token-weight dictionaries

        Returns:
            List of token_id-weight dictionaries
        """
        tokenizer = self._model.tokenizer
        result = []

        for weights in lexical_weights:
            converted = {}
            for token, weight in weights.items():
                # Convert token to ID
                token_id = tokenizer.convert_tokens_to_ids(token)
                if isinstance(token_id, int) and token_id != tokenizer.unk_token_id:
                    converted[token_id] = float(weight)
            result.append(converted)

        return result

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

        batch_size = batch_size or self._batch_size

        output = self._model.encode(
            texts,
            batch_size=batch_size,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        # Convert numpy arrays to lists
        dense = output["dense_vecs"].tolist()

        # Convert sparse format for Milvus
        sparse = self._convert_sparse_to_milvus_format(output["lexical_weights"])

        return EmbeddingResult(dense=dense, sparse=sparse)

    def encode_query(self, query: str) -> EmbeddingResult:
        """Encode a single query.

        Args:
            query: Query text

        Returns:
            EmbeddingResult with single embedding
        """
        return self.encode([query])
```

**완료 기준:**
- [ ] encode 메서드 구현
- [ ] Sparse vector 변환 구현
- [ ] encode_query 편의 메서드 구현
- [ ] batch_size 파라미터 지원

---

### Step 4: Factory 및 테스트 (1h)

**작업 내용:**
1. Singleton factory 함수
2. __init__.py 업데이트
3. 테스트 작성

**src/infrastructure/embedding/bge_m3.py (추가):**
```python
# Singleton instance
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
```

**src/infrastructure/embedding/__init__.py:**
```python
"""Embedding infrastructure."""
from src.infrastructure.embedding.bge_m3 import (
    EmbeddingResult,
    EmbeddingService,
    close_embedding_service,
    get_embedding_service,
)

__all__ = [
    "EmbeddingResult",
    "EmbeddingService",
    "close_embedding_service",
    "get_embedding_service",
]
```

**tests/unit/test_infrastructure/test_embedding_service.py:**
```python
"""Tests for embedding service."""
import pytest
from unittest.mock import MagicMock, patch

from src.infrastructure.embedding.bge_m3 import (
    EmbeddingResult,
    EmbeddingService,
)


class TestEmbeddingResult:
    """Tests for EmbeddingResult."""

    def test_empty_result(self) -> None:
        """Test empty result."""
        result = EmbeddingResult()
        assert len(result) == 0
        assert not result

    def test_result_with_data(self) -> None:
        """Test result with data."""
        result = EmbeddingResult(
            dense=[[0.1] * 1024],
            sparse=[{1: 0.5, 2: 0.3}],
        )
        assert len(result) == 1
        assert result


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_dimension(self) -> None:
        """Test dimension property."""
        service = EmbeddingService()
        assert service.dimension == 1024

    def test_device_detection(self) -> None:
        """Test device detection."""
        service = EmbeddingService()
        assert service.device in ["cuda", "cpu"]

    def test_not_loaded_initially(self) -> None:
        """Test model not loaded initially."""
        service = EmbeddingService()
        assert not service.is_loaded

    @patch("src.infrastructure.embedding.bge_m3.BGEM3FlagModel")
    def test_encode(self, mock_model_class: MagicMock) -> None:
        """Test encode method."""
        # Setup mock
        mock_model = MagicMock()
        mock_model.encode.return_value = {
            "dense_vecs": MagicMock(tolist=lambda: [[0.1] * 1024]),
            "lexical_weights": [{"test": 0.5}],
        }
        mock_model.tokenizer.convert_tokens_to_ids.return_value = 123
        mock_model.tokenizer.unk_token_id = 0
        mock_model_class.return_value = mock_model

        service = EmbeddingService()
        result = service.encode(["test text"])

        assert len(result) == 1
        assert len(result.dense[0]) == 1024
        assert 123 in result.sparse[0]

    def test_encode_empty_list(self) -> None:
        """Test encode with empty list."""
        service = EmbeddingService()
        result = service.encode([])
        assert len(result) == 0
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] __init__.py 업데이트
- [ ] 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_empty_result` | 빈 결과 생성 | len=0, bool=False |
| `test_result_with_data` | 데이터 있는 결과 | len=1, bool=True |
| `test_dimension` | 차원 확인 | 1024 |
| `test_device_detection` | 디바이스 감지 | cuda 또는 cpu |
| `test_encode` | 임베딩 생성 | dense+sparse 반환 |
| `test_encode_empty` | 빈 리스트 입력 | 빈 결과 |

### 4.2 Integration Tests (실제 모델)
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_real_encode` | 실제 모델 인코딩 | 1024차원 벡터 |
| `test_batch_encode` | 배치 인코딩 | N개 결과 |
| `test_korean_text` | 한국어 인코딩 | 정상 동작 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 모델 다운로드 시간 | Medium | Medium | 첫 로드 시 사전 안내, 캐시 활용 |
| GPU 메모리 부족 | High | Medium | batch_size 조정, CPU fallback |
| FlagEmbedding 버전 호환 | Medium | Low | 버전 고정, 테스트 자동화 |

---

## 6. Definition of Done

- [ ] `src/infrastructure/embedding/bge_m3.py` 구현
- [ ] EmbeddingResult 데이터 클래스 구현
- [ ] Lazy loading 구현
- [ ] Dense + Sparse 임베딩 동시 생성
- [ ] Batch 처리 지원
- [ ] CPU/GPU 자동 감지
- [ ] Sparse vector Milvus 포맷 변환
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 클래스 및 모델 | 0.5h | - |
| Step 2: 모델 로드/언로드 | 1h | - |
| Step 3: 임베딩 생성 메서드 | 1.5h | - |
| Step 4: Factory 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
