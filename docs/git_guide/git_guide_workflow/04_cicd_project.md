# 04. 프로젝트 CI/CD

## 추천 아키텍처

프로젝트에 적합한 배포 환경으로 **Azure Container Apps**를 추천합니다.

### 왜 Azure Container Apps인가?

| 항목 | Azure Container Apps | AKS | App Service |
|---|---|---|---|
| **복잡도** | 낮음 (서버리스) | 높음 (K8s 운영) | 중간 |
| **스케일링** | 자동 (0→N) | 수동/자동 | 자동 |
| **비용** | 사용한 만큼 | 항상 실행 | 항상 실행 |
| **컨테이너** | ✅ 네이티브 | ✅ 네이티브 | 제한적 |
| **Dapr 통합** | 기본 내장 | 별도 설치 | ✗ |
| **학습 곡선** | 낮음 | 높음 | 낮음 |
| **추천 대상** | 소규모 팀, 마이크로서비스 | 대규모 운영 | 단일 앱 |

> Container Apps = "AKS의 간편 버전"
> Kubernetes 없이도 컨테이너 기반 배포가 가능합니다.

---

## CI/CD 파이프라인 설계

### 전체 흐름

```
[Push to dev] ──► CI ──────────────────► CD
                   │                      │
                   ├─ Lint (ruff)         ├─ ACR에서 Pull
                   ├─ Format (black)     ├─ Container Apps 배포
                   ├─ Test (pytest)      └─ Health check
                   └─ Docker Build + ACR Push
```

### CI 워크플로우

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Lint
        run: uv run ruff check src/

      - name: Format check
        run: uv run black --check src/

      - name: Type check
        run: uv run ty check src/
        continue-on-error: true  # ty는 아직 alpha

      - name: Test
        run: uv run pytest tests/ -v

  docker-build:
    needs: lint-and-test
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login to ACR
        uses: azure/docker-login@v2
        with:
          login-server: ${{ secrets.ACR_LOGIN_SERVER }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Build and push
        run: |
          cd adf/custom_activity
          docker build -t ${{ secrets.ACR_LOGIN_SERVER }}/adf-custom:${{ github.sha }} .
          docker push ${{ secrets.ACR_LOGIN_SERVER }}/adf-custom:${{ github.sha }}
```

### CD 워크플로우

```yaml
# .github/workflows/cd.yml
name: CD - Deploy to Container Apps

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [dev]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - name: Login to Azure
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Deploy to Container Apps
        uses: azure/container-apps-deploy-action@v2
        with:
          acrName: ${{ secrets.ACR_NAME }}
          containerAppName: 3dt-app
          resourceGroup: 3dt-2nd-team1
          imageToDeploy: ${{ secrets.ACR_LOGIN_SERVER }}/app:${{ github.sha }}
```

---

## GitHub Secrets 설정

Repository → Settings → Secrets and variables → Actions에서 설정:

| Secret Name | 값 | 용도 |
|---|---|---|
| `ACR_LOGIN_SERVER` | `yourname.azurecr.io` | ACR 주소 |
| `ACR_USERNAME` | ACR admin username | ACR 인증 |
| `ACR_PASSWORD` | ACR admin password | ACR 인증 |
| `AZURE_CREDENTIALS` | Service Principal JSON | Azure login |
| `ACR_NAME` | ACR 이름 (without .azurecr.io) | Container Apps |

### Service Principal 생성

```bash
az ad sp create-for-rbac \
  --name "github-actions-sp" \
  --role contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/3dt-2nd-team1 \
  --sdk-auth
```

출력된 JSON을 `AZURE_CREDENTIALS` Secret에 저장합니다.

---

## 환경 분리 전략

| 환경 | 브랜치 | 용도 |
|---|---|---|
| **dev** | `dev` | 개발·테스트 |
| **prod** | `main` | 프로덕션 |

### 분리 방법

- `dev` push → dev 환경에 자동 배포
- `main` push → prod 환경에 자동 배포 (수동 승인 추가 가능)

```yaml
# 환경별 분기 예시
- name: Set environment
  run: |
    if [ "${{ github.ref }}" == "refs/heads/main" ]; then
      echo "ENV=prod" >> $GITHUB_ENV
    else
      echo "ENV=dev" >> $GITHUB_ENV
    fi
```

---

## 도입 로드맵

| 단계 | 내용 | 시기 |
|---|---|---|
| 1 | CI 구성 (lint + test + build) | M1 |
| 2 | ACR Docker push 자동화 | M2 |
| 3 | Container Apps 배포 | M3 |
| 4 | prod 환경 분리 | M4 |
