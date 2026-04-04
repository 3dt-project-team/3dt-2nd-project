# 구현 계획

## 프로젝트 목표
Azure Data Factory, Databricks, ML Studio를 활용한 데이터 파이프라인 구축 및 ML 모델 운영.
데이터 저장소: ADLS Gen2 (레이크) + Azure Database for PostgreSQL (서빙).

## 마일스톤

### M1: 인프라 설정
- [ ] Azure Key Vault 생성 및 시크릿 등록 (`adls-account-name`, `pg-connection-string` 등)
- [ ] ADLS Gen2 컨테이너 구성 (`raw` / `curated` / `feature`)
- [ ] Azure Database for PostgreSQL 스키마 정의
- [ ] Managed Identity 권한 설정 (ADLS, PostgreSQL, Key Vault)

### M2: 데이터 수집 (ADF)
- [ ] Linked Service 연결 구성 (ADLS, PostgreSQL, Key Vault)
- [ ] 원본 데이터 수집 파이프라인 구현 → `adf/` 폴더에 JSON 저장
- [ ] 트리거 설정 (스케줄 또는 이벤트 기반)

### M3: 전처리 (Databricks)
- [ ] 클러스터 Init Script 등록 (`notebooks/init_script_install_uv.sh`)
- [ ] vault_manager 연동 및 ADLS Spark conf 설정
- [ ] 데이터 클렌징·변환 → `curated/` 저장
- [ ] 피처 엔지니어링 → `feature/` 저장

### M4: 모델링 (ML Studio)
- [ ] 컴퓨팅 클러스터 구성
- [ ] Feature 데이터 Datastore 등록
- [ ] 학습 잡 제출 (`src/models/aml_train_example.py` 참고)
- [ ] MLflow 실험 트래킹 + Git commit hash 태깅

### M5: 서빙
- [ ] 예측 결과 Azure Database for PostgreSQL 적재
- [ ] 최종 파이프라인 End-to-End 검증

## 관련 문서
- 아키텍처 개요: [architecture.md](architecture.md)
- uv 통합 가이드: [uv_integration_guide.md](uv_integration_guide.md)
- 협업 규칙: [../docs/git_guide/](git_guide/)
