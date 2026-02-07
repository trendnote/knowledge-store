# Task 3.1.4: Hybrid Search API 통합

## 작업 정보
- **Task ID**: 3.1.4
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 14:46:37
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/23
- **Task Plan**: docs/task-plans/task-3.1.4-plan.md

## 작업 개요
RRF(Reciprocal Rank Fusion) 기반 통합 검색 API를 구현합니다.

## 생성/수정된 파일

### 1. Search Service 확장
**파일**: `src/services/search_service.py`

#### DEFAULT_WEIGHTS (신규)
```python
DEFAULT_WEIGHTS: dict[SearchType, float] = {
    SearchType.DENSE: 1.0,
    SearchType.SPARSE: 0.8,
    SearchType.GRAPH: 0.6,
}
```

#### _calculate_rrf_scores (신규)
```python
def _calculate_rrf_scores(
    self,
    results_by_type: dict[SearchType, list[SearchHit]],
    k: int = 60,
) -> dict[str, dict[str, Any]]:
    """Calculate RRF scores for all results.

    RRF(d) = Σ 1 / (k + rank_i(d))
    """
```
- 각 검색 타입별 결과의 RRF 점수 계산
- 중복 청크는 점수 합산
- sources에 각 타입별 원본 점수와 순위 저장

#### _merge_search_results (신규)
```python
def _merge_search_results(
    self,
    results_by_type: dict[SearchType, list[SearchHit]],
    top_k: int,
    weights: dict[SearchType, float] | None = None,
    rrf_k: int = 60,
) -> list[SearchHit]:
```
- 다중 검색 결과 RRF 병합
- 선택적 가중치 적용
- RRF 점수 기준 정렬 후 top_k 반환

#### unified_search (신규)
```python
async def unified_search(
    self,
    request: SearchRequest,
) -> SearchResponse:
```
- Dense, Sparse, Graph 병렬 실행
- asyncio.gather(return_exceptions=True) 사용
- 부분 실패 허용 (fail-safe)
- Over-fetch (top_k * 2) 후 병합

#### unified_search_with_weights (신규)
```python
async def unified_search_with_weights(
    self,
    request: SearchRequest,
    weights: dict[SearchType, float] | None = None,
) -> SearchResponse:
```
- 사용자 정의 가중치 적용
- 기본값: DEFAULT_WEIGHTS

#### suggest_weights (신규)
```python
def suggest_weights(self, query: str) -> dict[SearchType, float]:
```
- 쿼리 특성 기반 가중치 추천
- 짧은 쿼리: Sparse 선호
- 의미 검색 키워드("similar", "유사"): Dense 선호
- 일반 쿼리: 균형 가중치

#### search (신규)
```python
async def search(
    self,
    query: str,
    user_id: str,
    user_groups: list[str] | None = None,
    top_k: int = 10,
    search_types: list[SearchType] | None = None,
    min_score: float = 0.0,
) -> SearchResponse:
```
- unified_search 편의 메서드
- 간단한 호출 인터페이스 제공

### 2. Unit Tests 확장
**파일**: `tests/unit/test_services/test_search_service.py`

#### 신규 테스트 클래스
- `TestRRFCalculation`: 3개 테스트
  - 단일 타입 RRF 점수 계산
  - 다중 타입 RRF 점수 합산
  - 중복 청크 병합
- `TestMergeSearchResults`: 4개 테스트
  - 빈 결과 처리
  - top_k 제한
  - 가중치 적용
  - RRF 정렬
- `TestUnifiedSearch`: 5개 테스트
  - 전체 타입 검색
  - 선택 타입 검색
  - 부분 실패 처리
  - min_score 필터
  - 빈 타입 기본값
- `TestUnifiedSearchWithWeights`: 2개 테스트
- `TestSuggestWeights`: 4개 테스트
- `TestSearchConvenienceMethod`: 2개 테스트

**총 80개 테스트, 100% PASSED**

## 기술적 특징

### 1. RRF (Reciprocal Rank Fusion)
```python
RRF(d) = Σ 1 / (k + rank_i(d))
# k = 60 (표준값)
# rank_i = 검색 타입 i에서의 순위 (1부터 시작)
```

### 2. 병렬 검색 실행
```python
import asyncio

results_list = await asyncio.gather(
    *task_list,
    return_exceptions=True  # 부분 실패 허용
)
```

### 3. Over-fetch 전략
```python
# 병합 전 각 타입에서 top_k * 2 결과 가져옴
tasks[SearchType.DENSE] = self.dense_search(
    ...,
    top_k=request.top_k * 2,  # Over-fetch
)
```

### 4. 가중치 기반 점수 조정
```python
weighted_hit = SearchHit(
    ...,
    score=r.score * weight,  # 가중치 적용
)
```

## 테스트 결과

```
============================== test session starts ==============================
80 passed in 0.55s

Coverage:
- src/services/search_service.py: 90%
- src/domain/search.py: 100%
```

## 검색 흐름

```
1. 사용자 요청: unified_search(request)
2. 검색 타입 결정: request.search_types 또는 기본값
3. 병렬 실행:
   - Dense Search → list[SearchHit]
   - Sparse Search → list[SearchHit]
   - Graph Search → list[SearchHit]
4. 결과 수집: asyncio.gather (부분 실패 허용)
5. RRF 병합: _calculate_rrf_scores → _merge_search_results
6. 후처리: min_score 필터링
7. 반환: SearchResponse
```

## Dense vs Sparse vs Graph vs Unified 비교

| 특성 | Dense | Sparse | Graph | Unified |
|------|-------|--------|-------|---------|
| 기반 | 의미 벡터 | 키워드 | 관계 | RRF 융합 |
| 메트릭 | COSINE | IP | 경로 깊이 | RRF 점수 |
| 강점 | 의미적 유사성 | 정확 매칭 | 관계 탐색 | 균형 |
| 약점 | 키워드 누락 | 의미 한계 | 성능 | 복잡성 |

## 다음 단계
- Task 3.2: Search API 엔드포인트 구현
- Task 3.3: Search 성능 최적화
