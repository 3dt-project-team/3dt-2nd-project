# SENSE 프로젝트 1부: 반도체 주가 예측 AI를 Azure로 만들기 — 배경과 전체 아키텍처 설계

> **시리즈**: Azure + Databricks + TimesFM으로 반도체 주가 예측 파이프라인 구축하기  
> **분류**: Architecture, Azure, Cloud Design, DataOps, MLOps  
> **작성일**: 2026년 4월 17일  

---

## 들어가며 — 왜 반도체 주가 예측 프로젝트를 시작했는가

2024~2025년, 반도체 시장은 전례 없는 격변의 시기를 보냈습니다. AI 붐으로 인한 HBM 수요 폭발, TSMC의 생산 능력 확장, 미국-중국 기술 패권 경쟁에 따른 수출 규제. 삼성전자와 SK하이닉스의 주가는 이 거시경제적 파도 위에서 때로는 예상치 못한 방향으로 급변했습니다.

전통적인 주식 분석은 두 가지 방향으로 나뉩니다. 재무제표와 업황을 들여다보는 **기본적 분석(Fundamental Analysis)**과, 차트와 보조지표를 읽는 **기술적 분석(Technical Analysis)**. 그런데 반도체 섹터에서는 제3의 요소가 점점 더 큰 영향력을 발휘하기 시작했습니다. 바로 **뉴스 감성(News Sentiment)**입니다.

"삼성전자, HBM4 수율 90% 달성" 한 줄 뉴스가 주가를 하루 만에 5% 끌어올리는 시장에서, 텍스트 정보를 수치화하지 않은 예측 모델은 절반의 시야밖에 가질 수 없습니다.

SENSE(Semiconductor Economic News & Sentiment Engine) 프로젝트는 이 세 가지 관점을 하나의 파이프라인으로 통합하는 도전이었습니다.

**"글로벌 반도체 매크로 + 기술적 지표 + 뉴스 감성을 모두 먹는 앙상블 예측 엔진을 만들자."**

6인 팀이 2주 동안 Azure 위에서 이 시스템을 설계하고 구현한 과정을 이 시리즈에서 기록합니다.

---

## 1. 기존 주가 예측 접근법의 한계 — 우리가 풀려고 했던 문제

### 1.1 단일 모달리티의 벽

대부분의 시계열 예측 모델은 **가격 데이터만** 사용합니다. ARIMA, LSTM, Prophet 등이 대표적입니다. 이 모델들은 과거 가격의 패턴에서 미래를 유추하지만, 근본적인 한계가 있습니다: **가격이 반응하기 전의 선행 신호를 포착하지 못한다는 것**입니다.

반도체 주가는 분기 실적 발표, 수출 통계, 경쟁사 실적, 미국 금리 인상 등 다양한 외부 신호에 민감하게 반응합니다. 이 신호들은 가격 차트에 반영되기 전에, 뉴스 텍스트와 경제 데이터에 먼저 나타납니다.

### 1.2 정적 가중치의 함정

앙상블 모델을 사용하더라도, 대부분의 구현은 **고정 가중치(Fixed Weights)**를 사용합니다. 하지만 시장 국면은 고정되어 있지 않습니다. RSI 30 이하의 과매도 구간에서는 추세 추종보다 평균 회귀가 더 신뢰할 만합니다. 반대로 강한 모멘텀이 지속되는 트렌드 장세에서는 추세 모델이 우월합니다.

이 동적인 시장 국면을 무시하고 똑같은 가중치를 적용하는 것은, 날씨에 상관없이 매일 같은 옷을 입는 것과 다름없습니다.

### 1.3 뉴스 데이터 활용의 어려움

뉴스 텍스트를 주가 예측에 사용하려는 시도는 많았습니다. 그러나 대부분 단순 긍정/부정 이진 분류(Positive/Negative)에 그칩니다. "삼성전자 HBM3E 수율 70% 달성"이라는 뉴스가 '긍정'인지 '부정'인지는 맥락에 따라 다릅니다 — 경쟁사 HYNIX가 90%를 달성한 상황이라면 이 뉴스는 실망스러운 것입니다.

우리는 **ABSA(Aspect-Based Sentiment Analysis, 속성 기반 감성 분석)**를 도입했습니다. 기사 하나에서 '수율', '수요', '규제', '경쟁'처럼 여러 속성(Aspect)을 분리하고, 각 속성별로 독립적인 감성 점수를 산출합니다. 이것이 단순 감성 분류와의 근본적인 차이입니다.

---

## 2. 전체 Azure 에코시스템 아키텍처

SENSE는 크게 **데이터 수집 레이어**, **Medallion 저장 레이어**, **ML 처리 레이어**, **서빙 레이어** 네 계층으로 구성됩니다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SENSE — 전체 아키텍처 다이어그램                        │
└─────────────────────────────────────────────────────────────────────────────┘

  [외부 데이터 소스]
  ┌─────────────────────────────────────────────────────────────────────────┐
  │  야후 파이낸스    FRED API      네이버 뉴스 API    Google News RSS   관세청 API   │
  │  (OHLCV 10종)  (금리 6종)    (반도체 뉴스 본문)   (글로벌 뉴스)   (HS 8542 수출입)  │
  └────────┬──────────┬─────────────────┬───────────────┬───────────────────┘
           │           │                 │               │
           ▼           ▼                 ▼               ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                    Azure Data Factory (오케스트레이션 레이어)                │
  │                                                                          │
  │  타이머 트리거: 매일 16:30 KST                                             │
  │  ┌─────────────────────┐  ┌─────────────────────┐  ┌──────────────────┐ │
  │  │  Custom Activity     │  │  Functions Activity  │  │  ACI Activity    │ │
  │  │  (Yahoo / FRED /     │  │  (네이버 뉴스 +       │  │  (Google News    │ │
  │  │   관세청 수집)         │  │   환율 FX 수집)       │  │   Playwright     │ │
  │  └──────────┬───────────┘  └──────────┬──────────┘  │   one-shot)      │ │
  │             │                         │              └────────┬─────────┘ │
  └─────────────┼─────────────────────────┼───────────────────────┼───────────┘
                │                         │                       │
                └─────────────────────────┼───────────────────────┘
                                          │ 수집 결과 → ADLS Gen2
                                          ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                  ADLS Gen2 — Medallion 아키텍처 (3dtteam1adls)             │
  │                                                                          │
  │  raw/          curated/           feature/                               │
  │  원본 적재  →   전처리 완료    →   ML 피처 마트                             │
  │  (수집 즉시)    (01_raw_to_curated) (02_curated_to_feature)               │
  └────────────────────────┬─────────────────────────────────────────────────┘
                           │
                           ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                      Azure Databricks (sense-adb)                        │
  │                                                                          │
  │  01_raw_to_curated.py       02_curated_to_feature.py                    │
  │  - 결측치 보간               - 기술적 지표 계산 (RSI, ATR, 이격도)           │
  │  - 시계열 정렬               - ABSA 감성 분석 (Azure OpenAI)               │
  │  - 휴장일 통일               - TF-IDF 키워드 추출                          │
  │                             - 47개 피처 마트 구성                          │
  │                                                                          │
  │  ensemble_strategy.py (핵심)                                             │
  │  - TimesFM 2.5 XReg 추론    - AutoML UC BestTrial 추론                   │
  │  - Soft Switching 동적 가중치  - PostgreSQL 적재                          │
  └─────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                  Azure PostgreSQL (sense-pg-server)                      │
  │  fact_ensemble_forecast   agg_market_sentiment_daily   dim_news_master   │
  └────────────────────────────────────┬───────────────────────────────────┘
                                        │
                                        ▼
  ┌──────────────────────────────────────────────────────────────────────────┐
  │             sense-web (Flask 대시보드 + RAG 챗봇)                          │
  │             https://sense-web.azurewebsites.net                          │
  │             Azure App Service, Standard S1, Linux, koreacentral          │
  └──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 기술 스택 선택의 이유

### 3.1 Azure Data Factory — 오케스트레이션의 중심

데이터 수집 로직을 어디서 실행할 것인가. 이것이 아키텍처 설계 초반에 가장 많이 논의된 질문이었습니다.

처음 검토한 방식은 Databricks 노트북에서 직접 외부 API를 호출하는 것이었습니다. 간단하고 익숙하지만 두 가지 치명적인 문제가 있었습니다. 첫째, 수집 실패 시 재시도 로직을 직접 구현해야 합니다. 둘째, 수집·전처리·모델 실행이 하나의 노트북에 섞이면 유지보수가 불가능해집니다.

ADF를 선택한 이유는 세 가지였습니다:

**① 이질적인 수집기의 통합**: 우리 데이터 소스는 세 가지 형태였습니다. Python 스크립트가 필요한 Yahoo Finance/FRED 수집은 Custom Activity(Docker)로, 네이버 뉴스처럼 Event-driven으로 동작해야 하는 것은 Azure Functions로, Playwright 브라우저 자동화가 필요한 Google News는 ACI(Container Instances) one-shot으로. ADF의 Activity 시스템은 이 이질적인 실행 환경들을 하나의 파이프라인에서 오케스트레이션할 수 있었습니다.

**② 의존성 제어**: 수집이 완료된 후에 Databricks 전처리가 실행되어야 합니다. ADF의 Activity 의존성 체인(Activity Dependencies)이 이 순서를 보장합니다. 코드 없이 UI에서 화살표 하나로 설정 가능합니다.

**③ 빌트인 재시도 및 모니터링**: ADF는 Activity 단위 재시도 정책과 Azure Monitor 연동을 기본 제공합니다. 외부 API가 간헐적으로 실패하는 실제 환경에서 이 내결함성(Fault Tolerance)은 필수입니다.

### 3.2 ADLS Gen2 + Medallion 아키텍처

데이터 레이크 설계에서 가장 중요한 결정은 **Medallion 아키텍처**를 채택한 것이었습니다. raw → curated → feature의 3계층 구조는 Microsoft의 Modern Analytics Architecture 공식 권장 패턴이기도 합니다.

이 구조의 핵심 장점은 **되돌아갈 수 있다는 것**입니다. 전처리 로직에 버그가 발견되었을 때, raw 레이어의 원본 데이터는 손상되지 않았으므로 curated부터 재처리하면 됩니다. 피처 엔지니어링이 변경되었을 때는 feature 레이어만 재생성하면 됩니다. 각 레이어가 독립적인 체크포인트(Checkpoint) 역할을 합니다.

### 3.3 Azure Databricks — 왜 Spark가 필요했는가

데이터 규모가 크지 않은 초기 단계에서 Databricks를 선택하는 것은 오버엔지니어링처럼 보일 수 있습니다. 그러나 두 가지 이유가 결정을 이끌었습니다.

첫째, **Unity Catalog와 AutoML 통합**. Databricks AutoML이 실험을 실행하면 최적 모델이 자동으로 Unity Catalog에 등록됩니다. 이 모델을 `mlflow.sklearn.load_model("models:/…")`으로 바로 추론에 사용할 수 있는 MLOps 파이프라인이 완성됩니다.

둘째, **확장성**. 뉴스 데이터가 수십만 건으로 늘어나거나 대기업 수십 개로 종목을 확장하는 시나리오에서, Spark 기반 처리는 스케일 업이 설정 변경 수준에서 가능합니다.

---

## 4. 인증 아키텍처 — "소스 코드에 비밀이 없는" 원칙

보안 설계에서 우리가 세운 가장 중요한 원칙은 하나였습니다: **소스코드 어디에도 자격증명이 없어야 한다**.

이것은 선언에 그치지 않았습니다. pre-commit 훅에 `detect-secrets`를 설치하여, 누군가 실수로 API 키나 패스워드를 커밋하면 즉시 차단됩니다.

```
DefaultAzureCredential
       │
       ├─ 로컬 개발  : az login (개발자 계정)
       └─ 클라우드  : Managed Identity (패스워드 없는 서비스 인증)
              │
              ▼
        Azure Key Vault (kv-3dt-team1)
         ├─ adls-client-id / adls-client-secret  → ADLS Gen2 인증
         ├─ adls-account-name / adls-tenant-id   → 테넌트 정보
         ├─ pg-connection-string                 → PostgreSQL 연결
         ├─ azure-openai-endpoint                → ABSA / RAG 챗봇
         └─ azure-openai-key                     → Azure OpenAI API
```

`DefaultAzureCredential`의 핵심은 **환경에 따라 자동으로 인증 방식을 선택**한다는 것입니다. 로컬에서는 `az login`으로 인증된 개발자 계정을 사용하고, Databricks·App Service 같은 클라우드 환경에서는 Managed Identity를 사용합니다. 코드는 한 줄도 바꾸지 않습니다.

```python
# src/utils/vault_manager.py

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

class VaultManager:
    def __init__(self):
        credential = DefaultAzureCredential()  # 환경 자동 감지
        self._client = SecretClient(
            vault_url=os.environ["KEY_VAULT_URL"],
            credential=credential,
        )
    
    def get_secret(self, name: str) -> str | None:
        try:
            return self._client.get_secret(name).value
        except Exception:
            return None
    
    def get_pg_connection(self, engine: str = "psycopg"):
        conn_str = self.get_secret("pg-connection-string")
        if engine == "sqlalchemy":
            return create_engine(conn_str)
        return psycopg.connect(conn_str)
```

이 모듈 하나로 Databricks 노트북, Flask 웹앱, Azure Functions, ACI 컨테이너 — 어디서 실행하든 동일한 코드로 Key Vault 시크릿에 접근합니다.

---

## 5. 데이터 소스 설계 — 무엇을 왜 수집했는가

### 5.1 주가 데이터 (야후 파이낸스, 10개 종목)

| 티커 | 회사 | 역할 |
|---|---|---|
| `005930.KS` | 삼성전자 | 예측 타겟 |
| `000660.KS` | SK하이닉스 | 예측 타겟 |
| `NVDA` | NVIDIA | 글로벌 AI 반도체 선행지표 |
| `TSM` | TSMC | 파운드리 업황 |
| `MU` | Micron | DRAM 경쟁사 |
| `ASML` | ASML | 반도체 장비 선행지표 |
| `^SOX` | PHLX 반도체 지수 | 섹터 전체 센티먼트 |
| `KRW=X` | USD/KRW 환율 | 수출 기업 영향 |

TSMC가 NVIDIA로부터 받는 주문이 늘면 삼성전자 파운드리 부문에 경쟁 압력이 된다. ASML의 EUV 장비 수주 잔고가 줄면 파운드리 업황 위축의 선행 신호다. 이 글로벌 연쇄 반응을 피처로 표현하기 위해 경쟁사·밸류체인 데이터를 수집했습니다.

### 5.2 금리 데이터 (FRED, 6종)

| 시리즈 코드 | 의미 | 반도체와의 관계 |
|---|---|---|
| `DGS10` | 미국 10년물 국채 수익률 | 성장주 밸류에이션 할인율 |
| `DGS2` | 미국 2년물 국채 수익률 | 단기 자금 조달 비용 |
| `T10Y2Y` | 장단기 금리차 (수익률 곡선) | 경기 침체 예측 지표 |
| `BAMLH0A0HYM2` | 하이일드 스프레드 | 시장 리스크 오프 신호 |
| `DFF` | 연방기금금리 | Fed 통화정책 기준 |
| `DFII10` | 실질 금리 (10년) | 인플레이션 조정 할인율 |

금리 데이터는 일별로 수집하여 `sense_macro` 파생변수 계산의 기반이 됩니다. `yield_spread`(10년-2년 스프레드), `risk_off_flag`(하이일드 스프레드 급등 여부), `macro_stress_score` 같은 23개 파생 리스크 시그널이 여기서 시작됩니다.

### 5.3 뉴스 데이터 — 두 채널의 역할 분리

네이버 뉴스와 Google News를 모두 수집한 이유는 **관점의 다양성** 때문입니다. 국내 반도체 기업에 대한 뉴스는 한국어 미디어가 훨씬 깊고 빠릅니다. 반면 글로벌 공급망 이슈, 미-중 반도체 제재, NVIDIA의 신제품 발표는 영문 미디어가 먼저 다룹니다.

네이버 뉴스는 Azure Functions로 API 기반 수집을 구현했고, Google News는 RSS 피드 파싱과 Playwright 브라우저 자동화가 조합된 컨테이너를 ACI one-shot으로 실행합니다.

### 5.4 관세청 수출입 통계 (HS Code 8542)

이것이 우리가 발굴한 가장 독특한 데이터 소스입니다. HS Code 8542는 "전자 집적회로(Integrated Circuits)"의 국제 통관 코드입니다. 한국 관세청은 이 코드별 수출·수입 금액과 수량을 월별로 공개합니다.

반도체 수출액의 등락은 삼성·SK하이닉스의 실적과 직결됩니다. 그리고 이 데이터는 기업 실적 발표보다 **한 달 앞서** 공개됩니다. 이 선행성을 포착한 변수 `semi_expDlr`, `semi_impDlr`가 Granger 인과관계 검정에서 통계적으로 유의미한 선행 신호임을 확인했습니다.

---

## 6. 프로젝트 운영 — GitHub Flow와 uv

### 6.1 브랜치 전략

6인 팀이 2주 동안 협업하는 프로젝트에서 브랜치 전략은 명확해야 합니다. 우리는 **GitHub Flow**를 채택했습니다. `dev`를 기본 브랜치로 삼고, 모든 작업은 feature 브랜치에서 이루어집니다. 직접 push는 없습니다. PR만 허용됩니다.

커밋 메시지는 Conventional Commit 규칙을 따릅니다: `feat(pipeline): add eventhub trigger`. pre-commit 훅의 commit-msg 단계에서 형식을 강제합니다.

### 6.2 uv 패키지 관리

Python 의존성 관리에 `uv`를 사용했습니다. pip 대비 10배 빠른 의존성 해결 속도가 CI/CD 환경에서 실질적인 차이를 만들었습니다. Python 3.11을 `pyproject.toml`에 고정하여 재현 가능한 빌드를 보장합니다.

```toml
[tool.uv]
python = "3.11"

[project.optional-dependencies]
ml = ["azure-ai-ml", "mlflow", "timesfm"]
databricks = ["databricks-sdk"]
```

`uv sync --extra ml`로 ML 관련 의존성만 설치하고, `uv sync --extra databricks`로 Databricks 관련만 설치할 수 있어, 각 실행 환경에 맞는 최소 의존성으로 컨테이너 이미지 크기를 줄였습니다.

---

## 마치며 — 다음 편 예고

이번 편에서는 SENSE가 왜 이 문제를 풀려고 했는지, 전체 Azure 아키텍처가 어떻게 생겼는지, 각 기술 선택의 이유는 무엇인지 살펴봤습니다.

다음 편에서는 이 아키텍처의 실제 구현 — ADF 파이프라인 설계, Medallion 레이어별 변환 로직, Azure Functions의 서버리스 수집기 구현을 상세히 다룹니다.

---

*SENSE 프로젝트 GitHub: https://github.com/3dt-project-team/3dt-2nd-project*  
*SENSE 웹 대시보드: https://sense-web.azurewebsites.net*
