# News Pipeline Notebooks

네이버/해외 뉴스 데이터를 **Bronze → Silver → Gold** 순서로 처리하는 Databricks 노트북 모음입니다.
ADF(Azure Data Factory)에서 각 노트북을 순서대로 호출합니다.

---

## 파이프라인 흐름

```
[ADF 트리거]
     │
     ▼
naver_news_preprocessing          Bronze 전체 재처리 (초기 적재용)
naver_news_preprocessing_incremental  Bronze → Silver 증분 처리 (매시간)
     │
     ▼
silver_preprocessed               Silver 전체 재처리 (초기 적재용)
silver_preprocessed_incremental   Silver 증분 처리 (매일)
     │
     ▼
Silver2Gold_Pipeline_incremental  Silver → Gold 증분 적재 (매일)
```

---

## 노트북 설명

### 1. `naver_news_preprocessing`
- **역할**: Bronze 네이버 뉴스 전체 데이터 전처리 (초기 1회성 적재)
- **입력**: `raw/news/naver/` (삼성전자, SK하이닉스 JSON)
- **출력**: `raw/news/naver/preprocessed/` (Parquet, year_month 파티션)
- **처리**: HTML 정리 → 중복 제거 → GPT-4.1-mini로 본문 3줄 요약(description) 생성

### 2. `naver_news_preprocessing_incremental`
- **역할**: Bronze → Silver 증분 처리, ADF에서 **매시간** 호출
- **입력**: `raw/news/naver/` (target_date, target_hour 파라미터)
- **출력**: `raw/news/naver/preprocessed/` (append 모드)
- **처리**: 기존 Silver 최신 수집 시간 기준으로 미처리 데이터만 선별 → HTML 정리 → GPT 요약
- **종료 조건**: 신규 데이터 없으면 `NO_NEW_DATA` 반환

### 3. `silver_preprocessed`
- **역할**: 네이버 + 해외(Google/Bing) 뉴스 전체 Feature 생성 (초기 1회성 적재)
- **입력**: `raw/news/naver/preprocessed/`, `silver/news/google_bing/preprocessed_google&bing/`
- **출력**: `silver/news/feature/` (Parquet, year_month 파티션)
- **처리**:
  - `text-embedding-3-small`으로 description 임베딩(summary_vector) 생성
  - `gpt-4.1-mini`로 ABSA 분석 (absa_aspect, absa_score, dynamic_keywords) 추출

### 4. `silver_preprocessed_incremental`
- **역할**: Silver Feature 증분 생성, ADF에서 **매일** 호출
- **입력**: 네이버 + 해외 preprocessed (target_date 파라미터)
- **출력**: `silver/news/feature/` (append 모드)
- **처리**: 기존 feature에 없는 URL만 선별 → 임베딩 → ABSA 분석 → append 저장
- **종료 조건**: 신규 데이터 없으면 `NO_NEW_DATA` 반환

### 5. `Silver2Gold_Pipeline_incremental`
- **역할**: Silver Feature → Gold PostgreSQL 증분 적재, ADF에서 **매일** 호출
- **입력**: `silver/news/feature/` (target_date 파라미터)
- **출력**: PostgreSQL `gold_news` 스키마 3개 테이블
- **처리**:
  - `dim_news_display`: 뉴스 리스트 서빙용 (sentiment_class, is_surge 포함)
  - `agg_market_sentiment_daily`: 종목별 일별 감성 집계 + TOP 10 키워드
  - `fact_feature_vector_store`: RAG/ML용 임베딩 벡터 및 키워드 모멘텀
- **보안**: PostgreSQL 접속 정보를 Key Vault(`pg-connection-string`)에서 파싱

---

## 공통 사항

| 항목 | 내용 |
|------|------|
| 런타임 | Azure Databricks |
| 인증 | Azure Key Vault (`vault_manager`) |
| 스토리지 | ADLS Gen2 (`3dtteam1adls`) |
| AI 모델 | GPT-4.1-mini (요약/ABSA), text-embedding-3-small (임베딩) |
| 파티션 | `year_month` 기준 월별 파티션 |
| 파라미터 | ADF에서 `target_date`, `target_hour` 주입 (없으면 KST 현재 시간 자동 설정) |
