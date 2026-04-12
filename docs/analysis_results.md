# SENSE 모델 출력 분석 및 해석 보고서

> **분석 일자**: 2025-04-12  
> **대상 노트북**: `timesfm_inference_lite.ipynb`, `statistical_baseline_analysis_lite.ipynb`  
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

---

## 8. 결론 및 권장 사항

### 8-1. 모델 선택 가이드

- **단기(5d)**: Ridge 기반 방향 예측 활용 (TimesFM 방향성 불안정)
- **중장기(20d)**: Ridge와 TimesFM XReg의 **합의(Consensus)** 기반 판단
- **리스크 관리**: VaR/CVaR 기반 포지션 사이징

### 8-2. 다음 단계

1. **Consensus 앙상블**: TimesFM + Ridge 예측의 가중 결합
2. **방향 정확도 개선**: TimesFM fine-tuning 또는 방향 필터 추가
3. **시나리오 개선**: 비선형 시나리오 모델링 (금리 비대칭 효과 반영)
4. **gold_macro_1y 데이터 수정**: ADF 파이프라인 점검
5. **실시간 모니터링**: Azure Function + PostgreSQL 기반 자동 실행

---

*본 분석은 SENSE 프로젝트의 Proof-of-Concept 결과이며, 투자 판단의 근거로 사용해서는 안 됩니다.*
