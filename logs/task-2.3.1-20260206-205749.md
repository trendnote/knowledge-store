# Task 2.3.1: Embedding Service 구현

## 작업 정보
- **Task ID**: 2.3.1
- **작업자**: Claude AI
- **작업일시**: 2026-02-06 20:57:49
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/17
- **Task Plan**: docs/task-plans/task-2.3.1-plan.md

## 작업 개요
BGE-M3 모델을 사용하여 Dense + Sparse 임베딩을 생성하는 서비스를 구현합니다.

## 생성된 파일

### 1. Embedding Service
**파일**: `src/infrastructure/embedding/bge_m3.py`

#### EmbeddingResult 데이터 클래스
```python
@dataclass
class EmbeddingResult:
    dense: list[list[float]]      # 1024 dim dense vectors
    sparse: list[csr_array]       # Milvus compatible sparse
    sparse_dict: list[dict[int, float]]  # dict format
```

#### EmbeddingService 클래스
- **Constants**:
  - `DIMENSION = 1024` (BGE-M3 dense dimension)
  - `VOCAB_SIZE = 30000` (sparse vector size)

- **Properties**:
  - `dimension` - 임베딩 차원 (1024)
  - `is_loaded` - 모델 로드 여부
  - `device` - CPU/GPU 자동 감지
  - `model_name` - 모델 이름

- **Methods**:
  - `encode(texts, batch_size) -> EmbeddingResult`
    - Dense + Sparse 동시 생성
    - Batch 처리 지원
  - `encode_query(query) -> EmbeddingResult`
    - 단일 쿼리 인코딩
  - `encode_documents(documents) -> EmbeddingResult`
    - 문서 배치 인코딩
  - `_load_model()` - Lazy loading
  - `unload()` - 모델 언로드 + GPU 캐시 정리

- **Features**:
  - Lazy Loading: 첫 호출 시에만 모델 로드
  - Context Manager: `with EmbeddingService() as service:`
  - Sparse Vector 변환: token -> token_id

#### Factory Pattern
- `get_embedding_service(model_name, use_fp16, batch_size) -> EmbeddingService`
- `close_embedding_service()` - 서비스 종료 및 메모리 해제
- `reset_embedding_service()` - 테스트용 리셋

**exports**: `src/infrastructure/embedding/__init__.py`

### 2. Unit Tests
**파일**: `tests/unit/test_infrastructure/test_embedding_service.py`

테스트 클래스:
- `TestEmbeddingResult`: 3개 테스트
- `TestEmbeddingServiceProperties`: 7개 테스트
- `TestEmbeddingServiceEncode`: 8개 테스트
- `TestEmbeddingServiceModelLoading`: 6개 테스트
- `TestSparseVectorConversion`: 3개 테스트
- `TestSingleton`: 5개 테스트

**총 32개 테스트, 100% PASSED**

## 기술적 특징

### 1. BGE-M3 모델 사용
```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel(
    "BAAI/bge-m3",
    use_fp16=True,  # 메모리 절약
    device="cuda",  # 자동 감지
)
```

### 2. Dense + Sparse 동시 생성
```python
output = model.encode(
    texts,
    batch_size=12,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=False,  # 불필요
)
# output['dense_vecs']: (N, 1024) 배열
# output['lexical_weights']: list[dict[str, float]]
```

### 3. Sparse Vector 포맷 변환
```python
# BGE-M3 출력: dict[str, float] (token -> weight)
{"the": 0.5, "embedding": 0.8}

# Milvus 요구: scipy.sparse.csr_array
# 변환: tokenizer.convert_tokens_to_ids() 사용
```

### 4. Lazy Loading
```python
def _load_model(self) -> None:
    if self._model is not None:
        return  # 이미 로드됨

    from FlagEmbedding import BGEM3FlagModel
    self._model = BGEM3FlagModel(...)
```

### 5. GPU 캐시 정리
```python
def unload(self) -> None:
    if self._model is not None:
        del self._model
        self._model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
```

## 테스트 결과

```
============================== test session starts ==============================
32 passed in 0.52s

Coverage:
- src/infrastructure/embedding/bge_m3.py: 97%
```

## 해결된 이슈

### 1. Ruff Lint Error
- **문제**: `SIM108 Use ternary operator`
- **해결**: if-else 블록을 ternary operator로 변경

### 2. Mock Patch 경로 문제
- **문제**: FlagEmbedding이 함수 내에서 import되어 모듈 레벨 patch 불가
- **해결**: `sys.modules`에 mock 모듈 추가하는 방식으로 변경

## 다음 단계
- Task 2.3.2: Chunking Service 구현
- Task 2.3.3: Entity Extraction Service 구현
