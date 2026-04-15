# SENSE RAG App

`src/service/app`은 SENSE 프로젝트용 설명형 RAG 서빙 프로토타입입니다.

이번 버전은 공유해주신 데이터 사전 기준으로 맞췄습니다. 핵심 원칙은 두 가지입니다.

- 가능하면 뷰가 아니라 베이스 테이블 기준으로 읽는다.
- 설계명과 실제 테이블명이 다른 부분은 실제 생성된 이름에 맞춘다.

## 현재 참조하는 데이터 소스

### 뉴스 Gold

- `gold_news.dim_news_display`
- `gold_news.agg_market_sentiment_daily`
- `gold_news.fact_feature_vector_store`

### 매크로 Gold

- `gold_macro.fact_yf_fx_fred_1y`

### 퀀트 / ML Gold

- `gold_ml.fact_quant_sox_sync`
- `gold_ml.fact_quant_memory_proxy`
- `gold_ml.gold_quant_pcr_signals`
- `gold_ml.gold_ml_feature_set`

### 예측 결과

- `public.fact_ensemble_forecast`
- `public.fact_stat_forecast`

## 왜 이렇게 잡았는가

- 데이터 사전상 `v_quant_daily_signals`, `v_daily_report_summary`는 미생성 상태라서 앱이 여기에 의존하면 깨질 수 있습니다.
- 그래서 앱 내부에서 직접 SOX, memory proxy, PCR을 조합하도록 바꿨습니다.
- 뉴스 감성 추이도 `gold_news.agg_market_sentiment_daily`에서 직접 7일 이동 평균을 계산합니다.
- `gold_ml.gold_ml_feature_set`의 날짜 컬럼은 문서와 SQL이 `trade_date / base_date`로 다르게 보이므로 둘 다 시도하는 fallback을 넣었습니다.

## 질의 흐름

1. `router.py`
질문을 `news / metric / forecast / hybrid`로 라우팅하고 종목/감성/카테고리를 추론합니다.

2. `retriever.py`
뉴스는 `summary_vec` 기반 하이브리드 검색, 정량 데이터는 실제 Gold 테이블에서 직접 조회합니다.

3. `prompts.py`
뉴스, 감성, 매크로, ML 피처, 예측, 퀀트 신호를 한 컨텍스트로 묶습니다.

4. `chatbot.py`
임베딩 생성 → 검색 → LLM 응답 생성 흐름을 오케스트레이션합니다.

5. `flask_adapter.py`
Flask route에서 바로 붙일 수 있는 요청 파싱 / HTTP 응답 포맷 변환 계층입니다.

## Flask 결합 포인트

웹 팀에서는 아래 함수만 붙이면 됩니다.

- `src.service.app.handle_chat_request_payload`
- `src.service.app.create_chat_http_response`

예시:

```python
from flask import jsonify, request

from src.service.app import handle_chat_request_payload


@web_bp.route("/api/chat", methods=["POST"])
def api_chat():
    body, status = handle_chat_request_payload(request.get_json(silent=True))
    return jsonify(body), status
```

## 챗봇 실행 과정

1. Flask route가 JSON body에서 `question`을 받습니다.
2. `flask_adapter.py`가 요청을 검증합니다.
3. `chatbot.py`가 질문을 정리하고 `router.py`로 라우팅합니다.
4. `config.py`가 `.env`와 Key Vault에서 DB / Azure OpenAI 설정을 읽습니다.
5. `llm.py`가 질문 임베딩을 생성합니다.
6. `retriever.py`가 뉴스 벡터 검색과 정량 데이터 조회를 수행합니다.
7. `prompts.py`가 뉴스, 감성, 매크로, 퀀트, 예측 데이터를 하나의 프롬프트로 묶습니다.
8. `llm.py`가 최종 답변을 생성합니다.
9. `flask_adapter.py`가 `answer`, `sources`, `snapshots` 중심의 HTTP 응답으로 압축합니다.

## 로컬 스모크 테스트

```bash
.\.venv\Scripts\python.exe -c "from src.service.app import create_chat_http_response; r=create_chat_http_response('SK하이닉스 하락 리스크 근거 기사와 매크로 신호를 요약해줘'); print(r['answer'])"
```

## 필요한 환경변수

### 최소 실행 필수

- 아래 2가지 중 1가지만 충족하면 됩니다.
- 방식 A: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE`
- 방식 B: `PG_CONNECTION_STRING` (또는 Key Vault 시크릿 `pg-connection-string`)

### 전체 RAG 응답 필수

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

### Key Vault 사용 시

- `KEY_VAULT_URL`
- 로컬 인증: `az login`
- 시크릿명 기본값
- `pg-connection-string`
- `azure-openai-key`
- `azure-openai-endpoint`
- `azure-openai-api-version`
- `azure-openai-chat-deployment`
- `azure-openai-embedding-deployment`
- 필요하면 `.env`에서 `SENSE_KV_*_SECRET_NAME`으로 시크릿명 오버라이드 가능
- 이 앱은 실행 시 워크스페이스의 `.azure-config/`를 `AZURE_CONFIG_DIR`로 사용합니다.
- 로컬에 `127.0.0.1:9` 프록시가 잡혀 있으면 자동으로 무시합니다.

### 선택

- `SENSE_DEFAULT_STOCK_KEYWORD`
- `SENSE_DEFAULT_STOCK_CODE`
- `SENSE_DEFAULT_TICKER`
- `SENSE_DEFAULT_NEWS_LIMIT`
- `SENSE_DEFAULT_HISTORY_DAYS`
- `SENSE_RERANK_POOL_MULTIPLIER`
- `SENSE_ANSWER_TEMPERATURE`
- `SENSE_DEFAULT_HORIZON_DAY`

앱 전용 예제 파일은 `src/service/app/.env.example`에 있습니다.

## 다음 확장 포인트

- `stock_keyword`가 실제 DB에서 한글/영문 혼용일 수 있으니 다중 alias 필터 추가
- 기사 full-text 검색(`tsvector`) 추가
- `risk_off_flag`, `is_high_risk` 같은 파생 라벨을 프롬프트에서 별도 요약
- 다종목 비교 질문 지원
- Flask blueprint 또는 service layer에 인증/로그 추적 추가
