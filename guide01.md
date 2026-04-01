## 1단계: 레포지토리 생성 및 구조 설계 (Repository Setup)

2주라는 짧은 기간에는 여러 개의 레포지토리를 관리하는 것보다, **하나의 레포지토리(Monorepo) 안에서 폴더를 나누어 관리**하는 것이 압도적으로 효율적입니다.

### ① 레포지토리 생성 및 환경 설정

1. Organization 페이지에서 `New Repository` 클릭 (예: `azure-data-project`)
2. **Public / Private:** Private 권장 (Azure 연동 시 보안 유지)
3. **Add .gitignore:** `Python` 템플릿 선택 (필수)
4. **기본 폴더 구조 세팅 (초기 세팅 담당자가 `main` 브랜치에 구성 후 Push):**

```
📦 azure-data-project
 ┣ 📂 adf                 # Azure Data Factory 파이프라인 JSON 코드 (ADF 연동용)
 ┣ 📂 src                 # Databricks 및 ML 공통 모듈 (.py)
 ┃ ┣ 📂 utils             # 데이터 클렌징, Key Vault 연동 등 공통 함수
 ┃ ┗ 📂 models            # ML 모델링 관련 스크립트
 ┣ 📂 notebooks           # 탐색적 데이터 분석(EDA), 실험용 노트북 (.ipynb)
 ┣ 📂 docs                # 회의록, 데이터 스키마 정의서, 아키텍처 다이어그램 등
 ┣ 📜 .gitignore          # 환경변수(.env), 로컬 데이터(*.csv) 업로드 방지
 ┣ 📜 pyproject.toml      # 공통 패키지 및 버전 명시 (uv 관리)
 ┗ 📜 README.md           # 프로젝트 개요 및 로컬 환경 세팅 가이드
```

---

## 2단계: 브랜치 전략 (GitHub Flow)

복잡한 Git Flow 대신, 빠르고 직관적인 **GitHub Flow**를 사용하세요. 핵심은 **`dev` 브랜치는 항상 에러 없이 실행 가능한 상태를 유지**하는 것입니다.

- **`dev` 브랜치:** 배포 가능하고 테스트가 완료된 최종 코드 (직접 Push 절대 금지 🚫)
- **`feature` 브랜치:** 각자 기능을 개발하는 브랜치
    - **네이밍 규칙:** `유형/이름-작업내용` (예: `feat/alice-data-cleansing`, `fix/bob-adf-error`)

> 💡 **PR (Pull Request) 필수화:** GitHub 레포지토리 설정(Settings) > Branches > Branch protection rules에서 `dev` 브랜치에 대해 **'Require a pull request before merging' (최소 1명 승인 필요)** 옵션을 켜두세요.

---

## 3단계: 기술 스택별 GitHub 연동 및 협업 가이드 (핵심 🔥)

Azure의 세 가지 주요 도구는 Git과 연동되는 방식이 다릅니다. 각 담당자는 아래 가이드를 숙지해야 합니다.

### 🛠️ 1. Azure Data Factory (데이터 엔지니어)

ADF는 UI에서 작업하지만 내부적으로는 JSON 코드로 저장됩니다. 여러 명이 동시에 같은 파이프라인을 고치면 병합(Merge) 충돌이 크게 발생하므로 각별한 주의가 필요합니다.

- **연동 방법:** ADF 좌측 탭 `Manage` > `Git configuration` > GitHub 선택 > Organization 및 레포지토리, Root 폴더(`/adf`) 지정
- **협업 프로세스:**
    1. 팀원이 ADF에 들어오면 좌측 상단 브랜치를 `dev`에서 본인의 **`feature` 브랜치로 변경**한 뒤 작업합니다.
    2. 파이프라인이나 데이터셋 추가 후 상단의 `Save`를 누르면 브랜치에 커밋됩니다.
    3. 작업이 끝나면 GitHub에서 `dev`로 PR을 날리고 Merge합니다.
    4. **(중요) Publish:** Merge가 완료되면 1명의 담당자가 ADF에서 `dev` 브랜치로 맞춘 뒤 **`Publish` 버튼**을 누릅니다. (이때 `adf_publish`라는 특수 브랜치가 자동 생성되며 실제 서비스에 배포됩니다.)
- ⚠️ **ADF 협업 주의사항:** "나 지금 OOO 파이프라인 건드린다!"라고 메신저에 미리 알리고 작업하세요. JSON 충돌은 해결하기 매우 까다롭습니다.

### 🧠 2. Azure Databricks (데이터 엔지니어 / 분석가)

Databricks는 **'Repos'** 기능을 통해 GitHub와 완벽하게 연동됩니다.

- **연동 방법:** 사용자 설정(User Settings) > `Linked accounts`에서 GitHub Personal Access Token(PAT) 등록 ➡️ 좌측 `Workspace` > `Repos`에서 레포지토리 Clone
- **협업 프로세스:**
    1. 각자의 Repos에서 하단 브랜치를 클릭해 `feature/이름-작업` 브랜치를 생성합니다.
    2. `/src` 폴더에 `.py` 모듈을 만들거나, `/notebooks`에서 전처리 코드를 짭니다.
    3. 수정이 완료되면 Databricks Repos UI에서 직접 `Commit & Push`를 진행합니다.
    4. GitHub에서 PR 생성 및 코드 리뷰 후 Merge합니다.
    5. 다른 팀원은 본인의 Repos에서 `Pull`을 받아 최신 코드를 동기화합니다.

### 🤖 3. Azure ML Studio (ML 엔지니어)

ML Studio의 Compute Instance는 클라우드에 띄워진 우분투(Ubuntu) 컴퓨터와 같습니다. JupyterLab 터미널을 이용해 Git을 관리합니다.

- **연동 방법:** ML Studio > Notebooks > `Terminal` 열기 ➡️ `git clone <레포지토리 주소>` 실행
- **협업 프로세스:**
    1. 터미널에서 `git checkout -b feature/이름-모델링` 으로 브랜치를 땁니다.
    2. 노트북 파일을 열고 모델 학습 및 하이퍼파라미터 튜닝을 진행합니다.
    3. 튜닝이 끝나면 터미널에서 `git add .` ➡️ `git commit` ➡️ `git push` 진행
- 💡 **MLflow + Git 꿀팁:** ML Studio에서 실험을 돌릴 때, **현재 Git Commit Hash 값을 MLflow 태그로 기록**하세요. 나중에 "정확도 95% 나왔던 모델 코드가 뭐였지?" 할 때, 커밋 번호만 보면 그 시절의 코드로 바로 돌아갈 수 있습니다.

---

## 4단계: 6인 팀의 GitHub 협업 약속 (Ground Rules)

이 규칙들을 프로젝트 첫날 팀원들과 합의하고 README.md에 적어두세요.

**1. 커밋 메시지 통일 (Conventional Commits)**
무엇을 작업했는지 한눈에 알아볼 수 있도록 말머리를 답니다.

- `feat: 데이터 클렌징 함수 추가` (새로운 기능, 코드)
- `fix: ADF DB 연결 권한 에러 해결` (버그 수정)
- `docs: README 아키텍처 이미지 추가` (문서 작업)
- `refactor: 중복 전처리 로직 모듈화` (결과는 같지만 코드 구조 개선)

**2. PR (Pull Request) 규칙**

- PR 제목: `[Feat] OOO 기능 추가`
- PR 내용: (팀원들이 알 수 있도록 구체적으로 작성)
    - 어떤 문제를 해결했나요?
    - 무엇을 테스트해야 하나요? (예: "Databricks에서 `cleaner.py` 돌려보시면 됩니다.")
    - 관련된 이슈(선택): #이슈번호

**3. 데이터는 절대 GitHub에 올리지 말 것**

- 코드는 GitHub에, **데이터(CSV, Parquet 등)는 무조건 ADLS Gen2(Azure 스토리지)**에 있어야 합니다.
- `.gitignore`에 `.csv`, `.parquet`, `.env` 등이 잘 들어가 있는지 초기 세팅 시 꼭 확인하세요. `.env` 파일에 Key Vault URL이나 비밀번호를 하드코딩해서 올리면 보안 사고가 발생합니다.

---

### 🚀 다음 액션 플랜 제안

1. 팀원 중 한 분이 **레포지토리를 파고 기본 폴더 구조와 `.gitignore`를 세팅**하여 `dev`에 Push 하세요.
2. 팀원 모두가 각자의 Databricks와 ML Studio에 들어가 **해당 레포지토리를 Clone** 해보세요.
3. 아무 내용이나 적은 텍스트 파일을 각자 `feature` 브랜치에서 만들고, **PR을 날려 승인(Approve) 후 Merge 해보는 테스트**를 진행해 보세요. 이 워크플로우에 익숙해지는 데 하루 정도 투자하는 것이 2주 프로젝트를 살립니다!
