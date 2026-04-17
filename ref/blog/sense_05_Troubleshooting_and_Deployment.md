# SENSE 프로젝트 5부: P-C-S 트러블슈팅 및 Blue-Green 웹 배포

> **시리즈**: Azure + Databricks + TimesFM으로 반도체 주가 예측 파이프라인 구축하기  
> **분류**: Troubleshooting, MLOps, Azure App Service, Blue-Green Deployment, DevOps  
> **작성일**: 2026년 4월 17일  

---

## 들어가며 — "예상치 못한 데이터"가 진짜 공부다

2주짜리 프로젝트였습니다. 아키텍처를 설계하고, 파이프라인을 구축하고, 모델을 학습시키고, 웹 서비스를 배포하는 모든 과정이 14일 안에 이뤄졌습니다. 처음부터 계획대로 흘러간 날은 하루도 없었습니다.

그러나 그 장애들을 해결하는 과정에서 **설계 문서에서는 절대 배울 수 없는 것들**을 배웠습니다. 이번 편은 SENSE를 만들면서 만난 실제 장애들의 기록입니다.

각 케이스는 **P-C-S 프레임워크**로 기술합니다:
- **Problem (현상)**: 무엇이 잘못되었는가
- **Cause (원인)**: 왜 그 문제가 발생했는가
- **Solution (해결)**: 어떻게 해결했는가

---

## 케이스 1 — sklearn 역직렬화 오류: 클러스터 업그레이드의 함정

### Problem

Databricks 앙상블 노트북을 실행했을 때 다음 오류가 발생했습니다:

```
AttributeError: 'SimpleImputer' object has no attribute '_fill_dtype'
  File "ensemble_strategy.py", line 142, in run_ensemble_forecast
    uc_pred = model.predict(X)
```

직전까지 잘 작동하던 모델 추론 코드가 갑자기 실패했습니다.

### Cause

원인 추적은 다음 순서로 진행했습니다.

1. `model.__sklearn_version__` 확인 → `"1.4.2"`
2. 현재 클러스터 환경의 sklearn 버전 확인 → `"1.8.0"`
3. sklearn 1.8 릴리스 노트 확인

```python
# 원인 확인 코드
import sklearn
print(f"직렬화 버전: {model.__sklearn_version__}")
print(f"현재 환경: {sklearn.__version__}")
# 출력: 직렬화 버전: 1.4.2 / 현재 환경: 1.8.0
```

Databricks Runtime이 13.3 LTS에서 15.4 ML LTS로 업그레이드되면서 bundled sklearn 버전이 변경되었습니다. AutoML이 모델을 직렬화할 때 sklearn 1.4.2를 사용했는데, 로딩 환경은 1.8.0이었습니다.

**sklearn 1.8.0의 두 가지 주요 변경**:
1. `__sklearn_is_fitted__` 속성 필수화 — 1.4에서는 선택적이었음
2. `SimpleImputer._fill_dtype` 내부 속성 접근 방식 변경

### Solution

두 가지 선택지가 있었습니다:

- **A안**: AutoML을 새 클러스터 환경에서 재실행 (시간 소요: 60분 이상)
- **B안**: 재귀적 패치 함수 개발 (시간 소요: 2시간, 지식 습득 유리)

B안을 선택했습니다. 클러스터 환경을 제어할 수 없는 상황(프로덕션 공유 클러스터)에서도 동작하는 솔루션이 필요했기 때문입니다.

```python
def _deep_mark_fitted(estimator):
    """
    sklearn 1.4.x → 1.8.x 역직렬화 호환성 패치
    
    Pipeline, ColumnTransformer 같은 메타 추정기를 재귀적으로 순회하며
    1.8에서 요구하는 속성들을 사후 주입한다.
    """
    if not hasattr(estimator, "__class__"):
        return
        
    # (1) __sklearn_is_fitted__ 주입
    if not hasattr(estimator, "__sklearn_is_fitted__"):
        object.__setattr__(estimator, "__sklearn_is_fitted__", lambda: True)
    
    # (2) SimpleImputer._fill_dtype 복원
    if (estimator.__class__.__name__ == "SimpleImputer" and 
            hasattr(estimator, "statistics_") and 
            not hasattr(estimator, "_fill_dtype")):
        estimator._fill_dtype = estimator.statistics_.dtype
    
    # (3) 하위 추정기 재귀 처리
    sub_attrs = ["steps", "estimators_", "transformers_", 
                 "named_estimators_", "estimator"]
    for attr in sub_attrs:
        val = getattr(estimator, attr, None)
        if val is None:
            continue
        if isinstance(val, list):
            for item in val:
                # (name, estimator) 튜플 처리 (Pipeline.steps)
                if isinstance(item, tuple) and len(item) == 2:
                    _deep_mark_fitted(item[1])
                elif hasattr(item, "fit"):
                    _deep_mark_fitted(item)
        elif hasattr(val, "fit"):
            _deep_mark_fitted(val)
```

**핵심 교훈**: MLOps에서 모델 직렬화는 버전을 명시적으로 고정해야 합니다. 향후에는 모델 저장 시 `mlflow.sklearn.log_model(model, pip_requirements=["scikit-learn==1.4.2"])`로 의존성을 함께 로깅해야 합니다.

---

## 케이스 2 — SK하이닉스 R² = -1.19: 평균보다 못한 모델

### Problem

삼성전자 모델 R²=0.93, SK하이닉스 ElasticNet R²=-1.19. 이것은 "아무것도 모르는 사람이 그냥 과거 평균을 예측하는 것보다 이 모델이 더 나쁘다"는 의미입니다.

### Cause

원인을 파악하기 위해 예측값과 실제값의 산점도를 그렸습니다:

```python
# 진단 코드
import matplotlib.pyplot as plt

y_pred = enet_sk.predict(X_test)
y_true = y_test.values

plt.figure(figsize=(8, 6))
plt.scatter(y_true, y_pred, alpha=0.3)
plt.plot([y_true.min(), y_true.max()],   # 이상적 예측선
         [y_true.min(), y_true.max()], 'r--')
plt.xlabel("실제값 (T+20 로그수익률)")
plt.ylabel("예측값")
plt.title("SK하이닉스 ElasticNet 예측 vs 실제")
plt.savefig("/dbfs/diagnostics/sk_enet_scatter.png")
```

산점도를 보니 예측값이 실제값과 **반대 방향**으로 움직이고 있었습니다. 실제로 +10% 상승한 구간에서 모델은 -5%를 예측했습니다.

두 가지 복합 원인이 있었습니다:

**원인 1 — 스케일 불균형**: 학습 데이터에서 SK하이닉스 주가의 절대값(약 200,000원)이 글로벌 변수들의 Z-score 정규화 후 값(0~3 범위)보다 훨씬 컸습니다. ElasticNet의 L1 정규화가 상대적으로 큰 스케일의 주가 관련 계수를 과잉 억제했습니다.

**원인 2 — 피처-타겟 불일치**: 삼성전자로 학습된 피처 엔지니어링 로직이 SK하이닉스에 그대로 적용되었는데, 두 종목의 변동성 특성이 달랐습니다. SK하이닉스는 삼성전자보다 베타가 높아(시장 민감도 큼) 같은 RSI 임계값이 다른 의미를 가졌습니다.

### Solution

ElasticNet을 완전히 제거하고 **종목별 AutoML UC BestTrial**로 교체했습니다.

```python
# AutoML 실행 시 종목별 개별 실험 설정
for stock_code, stock_name in [("005930.KS", "삼성전자"), ("000660.KS", "SK하이닉스")]:
    summary = automl.regress(
        dataset=spark.table(f"sense_databricks.features.{stock_name}_t20"),
        target_col="target_log_return_20d",
        primary_metric="r2",
        timeout_minutes=60,
        # 각 종목이 독립적으로 최적 모델을 찾게 함
        experiment_dir=f"/Experiments/{stock_name}_automl_v2",
    )
    print(f"{stock_name}: {summary.best_trial.model_description} "
          f"R²={summary.best_trial.metrics['val_r2']:.4f}")

# 결과:
# 삼성전자: RandomForestRegressor R²=0.9266
# SK하이닉스: RandomForestRegressor R²=0.7097
```

---

## 케이스 3 — Silver vs Gold 피처 불일치: v0419의 주요 버그

### Problem

v0419 앙상블 결과가 v0416 대비 갑자기 MAPE(평균절대백분율오차)가 8%p 상승했습니다. 성능이 개선될 줄 알았던 배포가 오히려 악화된 것입니다.

### Cause

```
TimesFM 컨텍스트 읽기 소스: curated/ 레이어 (silver)
AutoML 학습 데이터 소스:    feature/ 레이어 (gold)
앙상블 추론 피처 소스:       feature/ 레이어 (gold) ← 불일치!
```

세 개의 노트북이 서로 다른 ADLS 레이어에서 데이터를 읽고 있었습니다:

- `01_raw_to_curated.py`: raw/ → curated/ (기본 정제)
- `02_curated_to_feature.py`: curated/ → feature/ (피처 엔지니어링)
- `03_ml_feature_build.py`: feature/ 읽어서 AutoML 실행
- `timesfm_inference.py`: **curated/ 직접 읽기** ← 버그

curated 레이어에는 KRX 거래일 보간, 이상치 처리, 로그수익률 계산이 적용되어 있지만, feature 레이어의 47개 파생변수(RSI, ATR, sense_macro 등)는 없습니다. TimesFM이 raw 시계열 컨텍스트를 읽고, UC 모델이 47개 피처 벡터를 읽으면 **두 모델이 서로 다른 "현실"을 보는 것**입니다.

### Solution

```python
# v0419 수정: 모든 소스를 Gold Layer로 통일
# timesfm_inference.py 수정

# Before (버그)
df_context = spark.table("sense_databricks.curated.samsung_ohlcv_daily")

# After (수정)  
df_context = spark.table("sense_databricks.features.samsung_gold_t20")
# features 테이블에는 curated 데이터 + 47개 파생변수가 모두 포함
```

추가로, 데이터 소스를 중앙에서 관리하는 설정 파일을 만들었습니다:

```python
# src/utils/data_sources.py
DATA_SOURCES = {
    "samsung": {
        "gold": "sense_databricks.features.samsung_gold_t20",
        "display": "sense_databricks.curated.samsung_ohlcv_daily",
    },
    "sk_hynix": {
        "gold": "sense_databricks.features.sk_hynix_gold_t20",
        "display": "sense_databricks.curated.sk_hynix_ohlcv_daily",
    }
}
```

---

## 케이스 4 — Date 인덱스 충돌 (v0418)

### Problem

```
KeyError: "None of ['date'] are in the columns"
  File "ensemble_strategy.py", line 89, in run_ensemble_forecast
    df.set_index('date', inplace=True)
```

### Cause

`date` 컬럼이 이미 인덱스로 설정된 상태에서 `set_index('date')`를 다시 호출했기 때문입니다. v0418에서 전처리 함수를 리팩토링하면서 `reset_index()` 호출 로직이 제거되었습니다.

### Solution

```python
# 조건 분기로 방어적 처리
def ensure_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """date가 인덱스에 있으면 컬럼으로 이동, 아니면 그대로 반환"""
    if df.index.name == "date":
        return df.reset_index()
    elif "date" in df.columns:
        return df
    else:
        # 인덱스를 date로 명명하거나 date 컬럼 생성 불가 → 에러
        raise ValueError(
            "DataFrame에 'date' 컬럼 또는 인덱스가 없습니다. "
            f"실제 인덱스 이름: {df.index.name}, 컬럼: {list(df.columns)}"
        )
```

---

## 케이스 5 — Staging Slot 503 오류: 3개 앱 설정 누락

### Problem

`az webapp deployment slot swap`으로 Staging → Production 슬롯 교체 후, Staging 슬롯이 HTTP 503을 반환했습니다. 웹 대시보드가 완전히 다운된 것처럼 보였습니다.

### Cause

Azure App Service의 슬롯(Slot)은 독립적인 환경 변수를 가집니다. Slot Swap 이후 Staging 슬롯은 이전 Production 설정을 갖게 되는데, 여기에 세 가지 환경 변수가 누락되어 있었습니다:

| 누락된 앱 설정 | 역할 |
|---|---|
| `KEY_VAULT_URL` | Azure Key Vault URL — 이 없으면 vault.py 초기화 실패 |
| `WEBSITES_PORT` | Flask 앱이 수신할 포트 (기본값과 다른 경우) |
| `acrUseManagedIdentityCreds` | ACR에서 이미지 풀링 시 Managed Identity 사용 |

Flask 앱 시작 시 `vault_manager.py`의 `DefaultAzureCredential` 초기화가 실패하고, 앱이 crashed 상태로 503을 반환한 것입니다.

**진단 방법**: Azure Portal → App Service → Staging 슬롯 → Log Stream에서 실시간 로그를 보면 다음과 같았습니다:

```
[ERROR] Failed to initialize VaultManager: 
  ManagedIdentityCredential.get_token failed: 
  Response status code 400. 
  KEY_VAULT_URL environment variable not set
Application startup failed. Exiting.
```

### Solution

```bash
# Staging 슬롯에 누락된 앱 설정 3개 추가
az webapp config appsettings set \
  --name sense-web \
  --resource-group 3dt-2nd-team1 \
  --slot staging \
  --settings \
    KEY_VAULT_URL="https://sense-kv.vault.azure.net/" \
    WEBSITES_PORT="8000" \
    acrUseManagedIdentityCreds="true"
```

추가 후 슬롯 재시작, 30초 후 헬스체크 통과, 503 해소.

**예방책**: Deployment 체크리스트에 "Staging 슬롯 앱 설정 동기화" 단계를 추가했습니다.

---

## sense-web Blue-Green 배포 파이프라인

### 배포 아키텍처

```
Local/CI ──→ az acr build ──→ ACR
                                │
                                ▼
                          Staging Slot (sense-web/staging)
                                │
                         헬스체크 HTTP 200?
                          YES  │  NO
                           ┌───┘  └────→ 롤백 (이전 이미지 유지)
                           ▼
                  az webapp deployment slot swap
                           │
                           ▼
                    Production Slot
                    (sense-web/production)
```

### 배포 스크립트

```bash
#!/bin/bash
# scripts/deploy.sh

set -euo pipefail  # 오류 시 즉시 중단

RESOURCE_GROUP="3dt-2nd-team1"
APP_NAME="sense-web"
ACR_NAME="sensecr"
IMAGE_TAG="${1:-latest}"  # 인수로 태그 지정, 기본값 latest

echo "===== SENSE Web 배포 시작: ${IMAGE_TAG} ====="

# 1. ACR Build — 로컬 Docker 불필요, Azure에서 빌드
echo "[1/5] ACR Build..."
az acr build \
  --registry "$ACR_NAME" \
  --image "sense-web:${IMAGE_TAG}" \
  --file Dockerfile \
  .

# 2. Staging 슬롯에 새 이미지 배포
echo "[2/5] Staging 슬롯에 새 이미지 배포..."
az webapp config container set \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --slot staging \
  --container-image-name "${ACR_NAME}.azurecr.io/sense-web:${IMAGE_TAG}"

# 3. Staging 재시작 및 대기
echo "[3/5] Staging 재시작..."
az webapp restart \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --slot staging

sleep 30  # 컨테이너 초기화 대기

# 4. 헬스체크
echo "[4/5] 헬스체크..."
STAGING_URL="https://${APP_NAME}-staging.azurewebsites.net/health"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL")

if [ "$HTTP_STATUS" != "200" ]; then
  echo "❌ 헬스체크 실패: HTTP ${HTTP_STATUS}. 배포 중단."
  exit 1
fi
echo "✅ 헬스체크 통과: HTTP ${HTTP_STATUS}"

# 5. Production으로 슬롯 교체
echo "[5/5] Production 슬롯 교체..."
az webapp deployment slot swap \
  --name "$APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --slot staging \
  --target-slot production

echo "===== 배포 완료: ${IMAGE_TAG} → Production ====="
```

### 왜 `az acr build`인가

로컬에서 `docker build` 후 `docker push`하는 전통적 방식 대신 `az acr build`를 사용한 이유:

1. **환경 재현성**: Azure Cloud Shell이나 로컬에 Docker Desktop이 없어도 빌드 가능
2. **속도**: ACR과 같은 Azure 데이터센터에서 빌드하므로 이미지 push 오버헤드 없음
3. **보안**: 빌드 환경에 민감한 Docker 컨텍스트가 로컬에 남지 않음

### Dockerfile 설계 결정

```dockerfile
FROM python:3.11-slim

# 시스템 의존성 최소화 — psycopg2 (postgresql 클라이언트)와 gcc (컴파일러) 필수
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*   # 레이어 크기 최소화

WORKDIR /app

# 의존성을 소스보다 먼저 복사 — 레이어 캐시 최적화
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# JSON 배열 형식 CMD — 셸 시그널 처리 문제 방지 (PID 1 보장)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", 
     "--worker-class", "gthread", "--threads", "4", "app:app"]
```

**JSON CMD 형식**: `CMD ["gunicorn", ...]`은 `CMD gunicorn ...` (shell form)과 달리 프로세스가 PID 1을 직접 받습니다. shell form은 `/bin/sh -c`가 PID 1이 되어 `SIGTERM` 시그널이 gunicorn에 전달되지 않아 **Graceful Shutdown이 안 됩니다**.

---

## sense-web 버전 이력

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| v1.0 | 4/14 | 최초 배포: 예측 대시보드 기본 UI, PostgreSQL 연결 |
| v1.1 | 4/16 | 앙상블 시각화 추가, 동적 가중치 차트 |
| v1.2 | 4/17 | **한/영 병기 접근성 레이블** (Semantic HTML + aria-label), Confidence Score UI |

v1.2의 한/영 병기는 단순한 UI 개선이 아닙니다. 금융 도메인 용어(레짐, 이격도, 베타)를 한국어와 영어로 동시에 표기함으로써 **스크린리더 사용자와 비전문가 모두 이해**할 수 있게 했습니다.

---

## 프로젝트 전체 회고

2주 동안 총 5개의 Azure 서비스(ADF, ADLS Gen2, Databricks, App Service, Key Vault)와 2개의 컴퓨팅 서비스(Azure Functions, ACI)를 연결하는 엔드-투-엔드 데이터 파이프라인을 구축했습니다.

가장 많은 것을 배운 순간은 장애 앞에서였습니다. sklearn 버전 불일치 패치를 작성할 때, 직렬화 메커니즘의 내부 구조를 이해하게 되었습니다. Silver vs Gold 피처 불일치를 디버깅할 때, Medallion 아키텍처에서 레이어 엄격성이 왜 중요한지 몸으로 배웠습니다.

**SENSE 최종 예측 성능**:
- 삼성전자(005930.KS): R²=0.9266, MAPE=3.2%, 방향 정확도=71.4%
- SK하이닉스(000660.KS): R²=0.7097, MAPE=5.8%, 방향 정확도=62.3%

T+20일 주가 예측이라는 어려운 문제에서, 두 종목 모두 **랜덤 워크 기저선(방향 정확도 50%)을 유의미하게 초과**하는 성능을 달성했습니다.

이 시리즈가 Azure 데이터 파이프라인과 금융 ML을 공부하는 분들께 도움이 되길 바랍니다.
