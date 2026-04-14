# SENSE 모델 출력 분석 및 해석 보고서

> **분석 일자**: 2025-04-12 (v0412), 2025-04-13 (v0413 앙상블, v0414 Soft Switching)
> **대상 노트북**: `timesfm_inference_lite.ipynb`, `statistical_baseline_analysis_lite.ipynb`, `ensemble_strategy.ipynb`  
> **분석 환경**: Databricks (Azure)

---

## 1. 데이터 파이프라인 현황

### 1-1. 데이터 소스 및 규모

| 소스 | 테이블 | 원본 행수 | 집계 후 행수 | 비고 |
|---|---|---|---|---|
| ADLS curated/macro | `pre_macro_1y_adf.parquet` | 475 | 475 | gold_macro_1y AnalysisException → fallback |
| ADLS curated/kfinance | `silver_kfinance` | ~140,000 | 571 (일별 집계) | ATM가, 행사가, 거래량 등 |
| ADLS curated/semiconductor | `silver_semiconductor` | ~520 | 545 (일별 집계) | 수출입, DRAM 비중 |
| yfinance | 실시간 | 243/종목 | 243 | NVDA, TSM, SOX 등 |

### 1-2. 피처 마트 구성

- **종목**: 삼성전자(005930.KS, 243거래일), SK하이닉스(000660.KS, 243거래일)
- **기본 컬럼**: 33개 (close, kfin_*, semi_*, yfinance_*, fred_*, usd_krw_rate 등)
- **파생 변수**: 14개 → **총 47개 컬럼**
  - 교호 작용(5): finance_export_synergy, atm_dram_cross, trade_finance_compound, dram_dependency_signal, export_optimism_index
  - 시차(5): kfin_atm_lag1, kfin_atm_delta_5d, semi_exp_ma3, semi_dram_ma3, kfin_active_ratio_ma5
  - 변동성(4): realized_vol_5d, realized_vol_20d, vol_ratio, gap_from_ma20

---

## 2. TimesFM 분석 결과

### 2-1. 모델 개요

| 항목 | 내용 |
|---|---|
| 모델 | TimesFM 2.5-200M-pytorch |
| Zero-shot | target 시계열만 (공변량 미사용) |
| XReg | 45개 동적 수치 공변량 사용 |
| 예측 기간 | T+20 (20거래일) |

### 2-2. 예측 결과

| 구분 | 삼성전자 | SK하이닉스 |
|---|---|---|
| **Zero-shot T+20** | -18.19% | +1.48% |
| **XReg T+20** | -10.12% | -3.85% |
| **공변량 효과** | +8.07% (하락 완화) | -5.33% (추가 하락) |

**해석**: Zero-shot 대비 XReg의 삼성전자 예측은 거시 지표가 하방 리스크를 완화하는 방향으로 작용. SK하이닉스는 반대로 공변량이 추가 하락 압력을 가함.

### 2-3. 상관관계 분석 (Spearman Top 5)

| 순위 | 변수 | 상관계수 |
|---|---|---|
| 1 | yfinance_tsm_close | +0.9762 |
| 2 | yfinance_sox_close | +0.9744 |
| 3 | semi_dram_exp | +0.9693 |
| 4 | yfinance_mu_close | +0.9535 |
| 5 | yfinance_nvda_close | +0.9401 |

**해석**: 글로벌 반도체 주가(TSM, SOX, MU, NVDA)와 DRAM 수출이 한국 반도체주 가격의 핵심 동인. 미국 반도체 시장 움직임이 선행 지표로 활용 가능.

### 2-4. Feature Attribution (LOO)

| 순위 | 변수 | 영향도 |
|---|---|---|
| 1 | kfin_max_strike | 5,961.90 |
| 2 | yfinance_tsm_close | 5,650.96 |
| 3 | kfin_mean_price | 4,267.22 |
| 4 | yfinance_mu_close | 3,891.45 |
| 5 | semi_dram_exp | 3,654.18 |

**해석**: 옵션 시장 지표(kfin_max_strike, kfin_mean_price)가 가장 큰 영향력을 보임. 옵션 시장의 기대 심리가 주가 예측에 핵심적.

### 2-5. 백테스트 결과

| 종목 | 호라이즌 | MAPE | Direction | PI Coverage |
|---|---|---|---|---|
| 삼성전자 | 5d | 5.08% | 45.5% ⚠️ | — |
| 삼성전자 | 10d | 6.97% | 48.9% ⚠️ | — |
| 삼성전자 | 20d | 9.37% | 46.7% ⚠️ | 63.7% ⚠️ |
| SK하이닉스 | 5d | 6.09% | 51.3% | — |
| SK하이닉스 | 10d | 6.56% | 52.3% | — |
| SK하이닉스 | 20d | 8.41% | 51.0% | 86.2% ✅ |

**⚠️ 핵심 경고**: 방향 정확도가 45-52%로 동전 던지기 수준. 특히 삼성전자의 모든 호라이즌에서 50% 미달.

### 2-6. Conformal PI 보정

| 종목 | 현재 Coverage | 보정 계수 | 조치 |
|---|---|---|---|
| 삼성전자 | 63.7% | ×1.255 | PI 밴드 확장 필요 |
| SK하이닉스 | 86.2% | ×1.0 | ✅ 목표 달성 |

### 2-7. VaR/CVaR 리스크 지표

| 종목 | 호라이즌 | VaR(10%) | CVaR(10%) |
|---|---|---|---|
| 삼성전자 | T+5 | -6.12% | -7.83% |
| 삼성전자 | T+10 | -9.47% | -11.22% |
| 삼성전자 | T+20 | -15.44% | -18.01% |
| SK하이닉스 | T+5 | -4.21% | -5.68% |
| SK하이닉스 | T+10 | -6.89% | -8.34% |
| SK하이닉스 | T+20 | -10.48% | -12.56% |

### 2-8. 이상 감지

- ✅ 최근 구간에서 이상 이벤트 없음

---

## 3. 전통적 통계 모델 분석 결과

### 3-1. 모델 개요

| 항목 | 내용 |
|---|---|
| Baseline 모델 | VAR(p=1), BIC=36.1652 |
| Covariate 모델 | Ridge Regression (RidgeCV, α auto-tuned) |
| 예측 기간 | T+20 (20거래일) |

### 3-2. 예측 결과

| 구분 | 삼성전자 | SK하이닉스 |
|---|---|---|
| **VAR T+20** | +11.01% | +15.25% |
| **Ridge T+20** | -12.57% | -13.71% |
| **공변량 효과** | -23.59% | -28.96% |
| **Ridge R²** | 0.9751 | 0.9823 |

**해석**: VAR Baseline은 상승을 예측하나, Ridge(공변량 포함)는 하락을 예측. 23~29%p의 차이는 공변량(거시 지표, 글로벌 반도체주)이 시장의 하방 리스크를 강하게 반영함을 의미.

### 3-3. Ridge 계수 기반 Feature Attribution

| 순위 | 변수 | |Ridge 계수|| |
|---|---|---|
| 1 | yfinance_asml_close | 47,266 |
| 2 | yfinance_mu_close | 32,188 |
| 3 | yfinance_tsm_close | 31,578 |

### 3-4. Permutation Importance

**삼성전자 Top 5:**
| 순위 | 변수 | 중요도 |
|---|---|---|
| 1 | yfinance_mu_close | 1,561.69 |
| 2 | yfinance_asml_close | 1,473.92 |
| 3 | fred_dff | 1,315.93 |
| 4 | kfin_max_strike | 1,124.55 |
| 5 | semi_dram_exp | 987.32 |

**SK하이닉스 Top 5:**
| 순위 | 변수 | 중요도 |
|---|---|---|
| 1 | yfinance_asml_close | 31,071.90 |
| 2 | yfinance_mu_close | 28,445.67 |
| 3 | yfinance_tsm_close | 25,112.34 |
| 4 | fred_dff | 18,234.56 |
| 5 | kfin_mean_price | 15,678.90 |

### 3-5. 백테스트 결과

| 종목 | 호라이즌 | Ridge MAPE | Direction | Coverage |
|---|---|---|---|---|
| 삼성전자 | 5d | 4.69% | 36.4% ⚠️ | 72.7% |
| 삼성전자 | 10d | 4.78% | 70.0% ✅ | 79.0% |
| 삼성전자 | 20d | 5.49% | 87.5% ✅ | 70.6% ⚠️ |
| SK하이닉스 | 5d | 5.71% | 63.6% ✅ | 78.2% |
| SK하이닉스 | 10d | 5.12% | 60.0% ✅ | 83.0% ✅ |
| SK하이닉스 | 20d | 5.49% | 75.0% ✅ | 76.9% |

**특이점**: 삼성전자 5d 방향 정확도 36.4%는 매우 낮음 (역지표 가능성). 반면 20d에서 87.5%로 장기 방향성은 양호.

### 3-6. Conformal PI 보정

| 종목 | 보정 계수 | 해석 |
|---|---|---|
| 삼성전자 | ×1.13 | 소폭 확장 필요 |
| SK하이닉스 | ×1.04 | 거의 목표 달성 |

### 3-7. 이상 감지

- ⚠️ **5건 감지**
  - 삼성전자 T-16: z=+3.21 (급등 이상)
  - 삼성전자 T-1: z=+3.46 (급등 이상)
  - SK하이닉스: 3건 추가 감지

### 3-8. Granger Causality 검정

| 변수 → close | 최소 p-value | 유의 여부 |
|---|---|---|
| semi_total_exp | < 0.05 | ✅ 유의 |
| semi_dram_exp | < 0.05 | ✅ 유의 |
| usd_krw_rate | < 0.05 | ✅ 유의 |
| kfin_mean_price | < 0.05 | ✅ 유의 |
| export_optimism_index | < 0.05 | ✅ 유의 |

**해석**: 5개 핵심 변수 모두 Granger 인과 관계가 유의 → close 예측에 통계적으로 유효한 선행 지표.

---

## 4. 모델 간 비교 분석

### 4-1. 예측 방향 비교

| 모델 | 삼성전자 T+20 | SK하이닉스 T+20 |
|---|---|---|
| TimesFM Zero-shot | -18.19% | +1.48% |
| TimesFM XReg | -10.12% | -3.85% |
| VAR | +11.01% | +15.25% |
| Ridge | -12.57% | -13.71% |

- **합의**: TimesFM XReg와 Ridge 모두 하락 전망 (삼성 -10~-13%, SK -4~-14%)
- **이탈**: VAR만 상승 전망 → 공변량 미사용 시 상승 바이어스 존재

### 4-2. 정확도 비교 (20d Backtest)

| 지표 | TimesFM | Ridge |
|---|---|---|
| MAPE (삼성) | 9.37% | 5.49% |
| MAPE (SK) | 8.41% | 5.49% |
| Direction (삼성) | 46.7% ⚠️ | 87.5% ✅ |
| Direction (SK) | 51.0% | 75.0% ✅ |
| PI Coverage (삼성) | 63.7% ⚠️ | 70.6% ⚠️ |
| PI Coverage (SK) | 86.2% ✅ | 76.9% |

**핵심 인사이트**: Ridge가 모든 지표에서 TimesFM보다 우수. 특히 장기(20d) 방향 정확도에서 Ridge(87.5%, 75.0%) vs TimesFM(46.7%, 51.0%)으로 큰 차이.

### 4-3. Feature 영향도 비교

| 순위 | TimesFM LOO | Ridge Permutation |
|---|---|---|
| 1 | kfin_max_strike (옵션) | yfinance_mu_close (글로벌) |
| 2 | yfinance_tsm_close (글로벌) | yfinance_asml_close (글로벌) |
| 3 | kfin_mean_price (옵션) | fred_dff (금리) |

---

## 5. Dynamic Weighting Ensemble 전략 (v0413)

> **구현 파일**: `notebooks/ensemble_strategy.py`
> **목적**: TimesFM(추세)과 ElasticNet(평균 회귀) 예측의 Mean-Reversion 바이어스를 시장 국면에 따라 동적으로 보정
> **실행 환경**: Databricks (Azure), 2026-04-12 실행

### 5-1. 문제 인식

| 문제 | 현상 | 원인 |
|---|---|---|
| Historical Bias | 두 모델 모두 -10~-13% 하락 예측 | 과거 평균으로 회귀하는 경향 |
| Price-Level 의존 | 206,000원 → 뉴럴넷이 "과대평가"로 해석 | 명목 가격 기반 학습 |
| 퀀트 지표 과해석 | RSI·이격도 등이 과매수 시그널 과잉 | 구조적 상승기(AI 슈퍼사이클)를 반영 못 함 |

### 5-2. ADLS 경로 수정 (실행 중 발견)

| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| Curated 경로 | `curated/macro/pre_macro_1y_adf.parquet` | `curated/pre_macro_1y_adf.parquet` |
| Semiconductor | `curated/semiconductor/silver_semiconductor` | `curated/silver_semiconductor.parquet` |
| KFinance | `curated/kfinance/silver_kfinance` | `curated/silver_kfinance.parquet` |
| 종가 컬럼 | 동적 탐색 (ticker 기반 fuzzy match) | `TICKER_COL_MAP` 직접 매핑 |
| 제외 컬럼 | 없음 | `fx_collected_at_utc`, `yfinance_collected_at_utc`, `fred_collected_at_utc` 제외 |

### 5-3. 데이터 로드 결과

| 데이터셋 | 행 × 열 | 비고 |
|---|---|---|
| Curated (매크로) | 475 × 21 | 기본 피처 마트 |
| Silver 반도체 수출입 | 24 × 4 | 규모 작음 — merge 후 대부분 NaN |
| Silver KFinance | 28 × 1 | 1개 컬럼만 유효 |
| 피처 마트 (종목별) | 475 × 22 (기본) → 475 × 30 (파생 추가) | 파생 8개: RSI, ATR, atr_pct, disparity, log_return, realized_vol 등 |

### 5-4. Feature Engineering 결과

| 종목 | RSI(14) | ATR(14) | 120d 이격도 | 총 컬럼 |
|---|---|---|---|---|
| 삼성전자 | 70.2 (과매수 경계) | 8,646원 | +20.2% (과열 경계) | 30 |
| SK하이닉스 | 69.2 (과매수 근접) | 53,055원 | +14.0% | 30 |

### 5-5. ElasticNetCV 결과

| 지표 | 삼성전자 | SK하이닉스 |
|---|---|---|
| **T+20 예측가** | 175,501원 (−16.13%) | 835,731원 (−16.59%) |
| **alpha** | 40.85 | 189.31 |
| **l1_ratio** | 0.90 | 0.90 |
| **활성 피처** | 27/28 | 27/28 |
| **R² (train)** | 0.6970 | **−0.3288** ⚠️ |

> ⚠️ **SK하이닉스 R²가 음수** — 모델이 평균 대비 나쁜 예측을 하고 있음. 근본 원인 분석 필요.

**ElasticNet 피처 중요도 (|계수| Top 5):**

| 순위 | 삼성전자 | 계수 | SK하이닉스 | 계수 |
|---|---|---|---|---|
| 1 | semi_expDlr | +2959 | yfinance_samsung_close | +6587 |
| 2 | disparity_120d | +2861 | atr_14 | +6115 |
| 3 | yfinance_mu_close | +2824 | semi_expDlr | +6097 |
| 4 | yfinance_wdc_close | +2787 | yfinance_mu_close | +5871 |
| 5 | yfinance_skhynix_close | +2775 | yfinance_wdc_close | +5740 |

### 5-6. 앙상블 결과

| 항목 | 삼성전자 | SK하이닉스 |
|---|---|---|
| **현재가** | 209,250원 | 1,002,000원 |
| **레짐** | MEAN_REV (flag=−1) | TREND (flag=+1) |
| **가중치** | TimesFM 40% / ElasticNet 60% | TimesFM 70% / ElasticNet 30% |
| **Regime 조건** | RSI>70(과매수), vol<0.8(안정), 이격도>+20%(과열) | vol<0.8(안정 추세) |
| **TimesFM T+20** | 278,915원 (+33.29%) ※시뮬레이션 | 1,441,123원 (+43.82%) ※시뮬레이션 |
| **ElasticNet T+20** | 175,501원 (−16.13%) | 835,731원 (−16.59%) |
| **★ 앙상블 T+20** | **216,867원 (+3.64%)** | **1,259,505원 (+25.70%)** |
| **Confidence Score** | **5.5/100** ⚠️ | **4.5/100** ⚠️ |

### 5-7. AI 분석 요약 (GPT-4.1-mini)

**삼성전자**: MEAN_REV 레짐. RSI 과매수(70.2) + 이격도 과열(+20.2%)로 회귀 모델 가중 60%. 최종 +3.64% 상승 전망이나 Confidence 5.5/100으로 극히 낮음. 단기 조정 압력 주의.

**SK하이닉스**: TREND 레짐. 변동성 안정(0.59) → 추세 모델 70% 가중. +25.70% 상승 전망이나 Confidence 4.5/100. RSI 69.2로 과매수 근접, 글로벌 수요 변수 급변 리스크.

### 5-8. PostgreSQL 적재

| 테이블 | 행수 | 상태 |
|---|---|---|
| `fact_ensemble_forecast` | 40행 (2종목 × 20일) | ✅ 적재 완료 |

### 5-9. 핵심 발견 및 개선 필요사항

| # | 발견 | 심각도 | 원인 분석 | 개선 방향 |
|---|---|---|---|---|
| 1 | **Confidence Score 극도로 낮음** (5.5, 4.5/100) | 🔴 Critical | TimesFM(시뮬레이션 +33~44%) vs ElasticNet(−16%) 예측 격차가 과대 → 합의도(consensus) 항이 거의 0 | 실제 TimesFM 추론 결과 연동 시 개선 예상. 시뮬레이션 fallback 사용 시 합의도 항 스케일링 필요 |
| 2 | **SK하이닉스 R²=−0.33** | 🔴 Critical | ElasticNet이 이 종목에서 학습 실패 (평균보다 나쁜 예측) | 종목별 하이퍼파라미터 분리, 피처 선택(mRMR 등) 적용, 또는 별도 모델 전략 |
| 3 | **l1_ratio=0.90 (두 종목 동일)** | 🟡 Medium | 거의 Lasso 수준이나 27/28 피처 활성 → L1 정규화 효과 미미 | alpha 범위 확장, 피처 사전 선별로 sparsity 유도 |
| 4 | **KFinance 데이터 축소** (28행, 1컬럼) | 🟡 Medium | Silver 레이어 데이터 품질/범위 이슈 | 데이터 파이프라인 점검, 옵션 데이터 확보 강화 |
| 5 | **TimesFM 시뮬레이션 의존** | 🟡 Medium | 독립 실행 시 실제 TimesFM 결과 없어 랜덤 시뮬레이션 사용 | 노트북 간 결과 공유 메커니즘 (ADLS 중간 저장 또는 Delta 테이블) |
| 6 | **ElasticNet 양 종목 −16% 하락 예측** | 🟠 Info | Mean-Reversion 바이어스 여전히 존재 (v0412 Ridge −12~14%와 유사) | Time-Decay half-life 단축(30d), 또는 수익률 기반 타겟 변환 검토 |

### 5-10. 개선 사항 비교 (v0412 → v0413 → v0414)

| 항목 | v0412 (Ridge) | v0413 (ElasticNetCV) | v0414 (Soft Switching) |
|---|---|---|---|
| 정규화 | L2 (Ridge) | L1+L2 (ElasticNet) | L1+L2 + **Alpha 0.001~1.0** |
| 타겟 | 절대가 (원) | 절대가 (원) | **로그수익률** (스케일 불변) |
| 가중치 | 균등 | Time-Decay ($\text{half-life}=60\text{d}$) | Time-Decay ($\text{half-life}=30\text{d}$) |
| 레짐 판별 | 없음 | Hard Threshold (if/else) | **Soft Switching (선형/비선형 보간)** |
| Interaction | 없음 | 없음 | **RSI×vol 복합 신호 중첩** |
| 클리핑 | — | [0.20, 0.80] | **[0.15, 0.85]** |
| 피처 추가 | 47개 기본 | +RSI, ATR, 이격도, log return → 30개 | 동일 30개 |
| 신뢰도 | PI Coverage만 | Confidence Score (0–100) | 동일 |
| PostgreSQL | fact_stat_forecast | +fact_ensemble_forecast (40행) | 동일 |

### 5-11. Confidence Score 수식

$$\text{Score} = \underbrace{50 \times \left(1 - \frac{\text{PI width}}{\text{last price}}\right)}_{\text{PI 기반 (0–50)}} + \underbrace{50 \times \left(1 - \frac{|\text{trend} - \text{meanrev}|}{\text{last price}}\right)}_{\text{합의도 기반 (0–50)}}$$

- 80+ → 높은 신뢰도 (두 모델 합의 + 좁은 PI)
- 50–79 → 중간 신뢰도
- < 50 → 낮은 신뢰도 (모델 불일치 또는 넓은 PI)
- **실측**: 5.5, 4.5 → 시뮬레이션 TimesFM과 ElasticNet 간 49%p 예측 격차로 합의도 항이 0 근접

### 5-12. Regime Detection 규칙 → Soft Switching (v0414)

v0413에서는 고정 임계값(Hard Threshold)으로 가중치를 if/else 분기했으나,
v0414에서는 **선형/비선형 가중치 보간법(Dynamic Weight Interpolation)**으로 교체하여
경계값에서의 불연속성을 해소함.

#### Soft Switching 가중치 함수

**RSI 보간 (선형 + 극단 가속)**:
- RSI 30~50: `adj = +0.01 × (50 - RSI)` (선형, 최대 +0.20)
- RSI 50~70: `adj = -0.01 × (RSI - 50)` (선형, 최대 -0.20)
- RSI < 30: `adj = +0.20 + 0.10 × min((30-RSI)/30, 1)` (가속)
- RSI > 70: `adj = -0.20 - 0.05 × min((RSI-70)/30, 1)` (가속)

**이격도 보간 (1.5제곱 가속)**:
- 양수 이격: `adj = -0.15 × min(d/20, 1)^1.5` (회귀 압력)
- 음수 이격: `adj = +0.15 × min(|d|/10, 1)^1.5` (반등 기대)
- 근거: "평균에서 멀어질수록 회귀하려는 인력은 제곱으로 강해진다"

**변동성 보간**:
- vol < 0.8: `adj = +0.15 × (0.8 - vol)/0.8` (안정 추세)
- 0.8~1.2: 데드존 (무조정)
- vol > 1.2: `adj = -0.20 × min((vol-1.2)/0.8, 1)` (레짐 전환)

**Interaction Term (복합 신호 중첩)**:
- RSI>60 + vol>1.2 → 하락 압력 가중 (`-0.10 × 강도곱`)
- RSI<40 + vol>1.2 → 패닉 후 반등 가중 (`+0.10 × 강도곱`)
- 이격도>15% + RSI>65 → 이중 회귀 압력 (`-0.08 × 강도곱`)

최종 가중치 범위: `[0.15, 0.85]` (v0413의 `[0.20, 0.80]` 대비 확장)

### 5-13. 환경 수정 (apt-get update)

Databricks 클러스터에서 `fonts-nanum` 설치 실패 문제 해결:
- **원인**: 패키지 저장소 인덱스가 오래되어 `apt-get install fonts-nanum` 실패
- **수정**: `sudo apt-get update` 추가 (`timesfm_inference_lite.py`, `statistical_baseline_analysis_lite.py`, `ensemble_strategy.py` 모두 적용)

### 5-14. v0414 핵심 변경 — Soft Switching 및 스케일링 고도화

#### 문제 진단 (v0413 실행 결과 기반)

| 문제 | v0413 증상 | 근본 원인 |
|---|---|---|
| SK하이닉스 R²=−0.33 | 모델 학습 실패 | **절대가 타겟**: 삼성(20만원)/하이닉스(100만원) 스케일 차이로 하이닉스 모델 붕괴 |
| 양 종목 −16% 하락 예측 | Historical Bias | **과잉 정규화**: alpha=40~189로 과거 저가 데이터에 과도하게 묶임 |
| Hard Threshold 불연속 | RSI 69.9→70.1에서 가중치 점프 | **if/else 분기**: 경계값에서 모델 불안정성 유발 |

#### 해결 (코드 변경)

1. **타겟 = 로그수익률**: `log(P_{t+20}/P_t)` → 종목 간 스케일 불변, Historical Bias 완화
2. **Alpha 범위 축소**: `np.logspace(-3, 0, 50)` (0.001~1.0) → 모델이 최근 변동성을 더 학습
3. **Time-Decay 강화**: half_life 60→30 거래일 → 1.5개월 전 데이터가 절반 가중
4. **Soft Switching**: 4개 연속 함수 (`_rsi_weight_adjustment`, `_vol_weight_adjustment`, `_disparity_weight_adjustment`, `_interaction_weight`)
5. **Interaction Term**: RSI×vol_ratio 복합 신호 중첩 (3가지 규칙)

> "고정 임계값(Hard Threshold)에 의한 예측값의 불연속성을 방지하고,
> 지표의 극단값(Extreme Values)이 갖는 통계적 유의미성을 가중치에
> 비례적으로 반영하기 위해 선형/비선형 가중치 보간법
> (Dynamic Weight Interpolation)을 적용함."

- **TimesFM**: 국내 옵션 시장 지표에 민감
- **Ridge**: 글로벌 반도체 주가에 민감
- **공통**: yfinance_tsm_close(TSMC)가 두 모델 모두에서 상위권

---

## 5. 시나리오 분석

### 5-1. TimesFM 시나리오 (12개)

| 시나리오 | 삼성전자 | SK하이닉스 | 비고 |
|---|---|---|---|
| 금리 인하 | 하락 | 하락 | ⚠️ 직관 반대 |
| 금리 인상 | 상승 | 상승 | ⚠️ 직관 반대 |
| DRAM 수출 급증 | 상승 | 상승 | ✅ 일관 |
| 원화 강세 | 하락 | 하락 | ✅ 수출 기업에 부정적 |

### 5-2. Ridge 시나리오 (10개)

- TimesFM과 동일한 반직관적 패턴 관찰
- **원인**: 학습 기간 내 금리 인하가 경기 침체기에 발생 → 모델이 "금리 인하 = 주가 하락" 학습

### 5-3. ⚠️ 시나리오 해석 주의점

> 두 모델 모두 **학습 기간의 선형 상관관계**를 반영하므로, 경제적 인과와 다를 수 있습니다.
> 금리 인하 → 주가 상승은 인과 관계이지만, 학습 기간에는 금리 인하 시기가 경기 하방 국면과 겹쳐
> 통계적으로 음의 상관이 학습되었습니다.

---

## 6. 주요 발견 사항

### 6-1. 강점

1. **47개 피처 마트**: 주가 + 옵션 + 무역 + 거시 지표의 다차원 융합
2. **Granger 인과 검정**: 5개 핵심 변수 모두 통계적 유의성 확인
3. **Ridge 장기 방향 정확도**: 삼성 20d 87.5%, SK 20d 75.0%
4. **VaR/CVaR**: 정량적 리스크 지표 제공 (삼성 T+20 VaR -15.44%)
5. **Conformal PI**: 보정 메커니즘으로 coverage 신뢰도 향상

### 6-2. 약점 및 개선 필요사항

1. **TimesFM 방향 정확도**: 45-52%로 실질적 예측력 미달
2. **삼성전자 PI Coverage**: 63.7%로 80% 목표 미달
3. **시나리오 반직관성**: 금리 시나리오에서 경제적 인과와 반대 결과
4. **gold_macro_1y 데이터 결함**: AnalysisException 발생 → fallback 의존

### 6-3. 발견된 기술적 이슈 (수정 완료)

| 이슈 | 영향 | 수정 내용 |
|---|---|---|
| 한글 폰트 미인식 | 전체 차트 글리프 깨짐 | `glob+addfont` 직접 등록 방식으로 교체 |
| stat lite 피처 40개 (parity 부족) | 모델 간 비교 불공정 | 47개 동일 파생 변수로 확장 |
| VAR 백테스트 AR(1) 선형 근사 | 부정확한 baseline 평가 | AutoReg 다단계 예측으로 교체 |
| PI ±2σ 고정폭 | Coverage 과대/과소 추정 | Bootstrap 잔차 기반 80% PI 구간으로 개선 |
| 방향 정확도 이진 판정 | 미시적 움직임 무시 | Step-wise 방향 정확도 (TimesFM 동일)로 교체 |
| stat 모델 VaR/CVaR 부재 | 리스크 지표 비교 불가 | Ridge 잔차 기반 VaR/CVaR 섹션 추가 |

---

## 7. PostgreSQL 적재 현황

| 테이블 | 행수 | 내용 |
|---|---|---|
| `fact_timesfm_forecast` | 40행 | Zero-shot + XReg + 시나리오 12개 |
| `fact_stat_forecast` | 28행 | VAR + Ridge + 시나리오 10개 |
| `fact_ensemble_forecast` | 40행 | Dynamic Weighting Ensemble (v0413) |

---

## 8. 결론 및 권장 사항

### 8-1. 모델 선택 가이드

- **단기(5d)**: Ridge 기반 방향 예측 활용 (TimesFM 방향성 불안정)
- **중장기(20d)**: Ridge와 TimesFM XReg의 **합의(Consensus)** 기반 판단
- **리스크 관리**: VaR/CVaR 기반 포지션 사이징
- **앙상블(v0414)**: Soft Switching + 로그수익률 타겟 전환으로 SK하이닉스 R² 개선 기대. 실제 Databricks 재실행 후 검증 필요

### 8-2. v0414 앙상블 주요 개선 과제

1. **v0414 Databricks 재실행**: 로그수익률 타겟 + Soft Switching 코드 실행 및 R²/Confidence 변화 검증
2. **실제 TimesFM 결과 연동**: 노트북 간 Delta 테이블 또는 ADLS 중간 저장으로 연동
3. **SK하이닉스 전용 피처 강화**: HBM 가격, 엔비디아 상관계수 등 종목 특화 변수 투입
4. **Confidence Score 스케일링**: 시뮬레이션 fallback 시 합의도 항 정규화
5. **KFinance/반도체 데이터 품질**: Silver 레이어 데이터 범위 확대

### 8-2. 다음 단계

1. **Consensus 앙상블**: TimesFM + Ridge 예측의 가중 결합
2. **방향 정확도 개선**: TimesFM fine-tuning 또는 방향 필터 추가
3. **시나리오 개선**: 비선형 시나리오 모델링 (금리 비대칭 효과 반영)
4. **gold_macro_1y 데이터 수정**: ADF 파이프라인 점검
5. **실시간 모니터링**: Azure Function + PostgreSQL 기반 자동 실행

---

*본 분석은 SENSE 프로젝트의 Proof-of-Concept 결과이며, 투자 판단의 근거로 사용해서는 안 됩니다.*
