# 05. CI/CD 기초 (Fundamentals)

## CI/CD란?

| 용어 | 정의 | 핵심 |
|---|---|---|
| **CI** (Continuous Integration) | 코드 변경을 자주 통합하고 자동 테스트 | "push하면 자동으로 테스트" |
| **CD** (Continuous Delivery/Deployment) | 테스트 통과 후 자동 배포 | "merge하면 자동으로 배포" |

---

## 전체 자동화 흐름 (Azure 기준)

```
코드 Push / PR
      │
      ▼
┌─────────────────────────────┐
│  CI 단계 (GitHub Actions)   │
│  ✅ 코드 Checkout            │
│  ✅ 의존성 설치 (uv sync)    │
│  ✅ 린트 (ruff check)        │
│  ✅ 포맷 체크 (black --check) │
│  ✅ 테스트 (pytest)           │
│  ✅ 빌드                      │
│  ✅ Docker 이미지 빌드        │
│  ✅ ACR에 push               │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  CD 단계 (자동 배포)         │
│  ✅ ACR에서 이미지 pull       │
│  ✅ AKS / Container Apps 배포│
│  ✅ 헬스 체크                 │
│  ✅ 배포 완료 알림            │
└─────────────────────────────┘
```

---

## GitHub Actions 기본 구조

GitHub Actions는 `.github/workflows/` 디렉토리에 YAML 파일로 정의합니다.

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

      - name: Test
        run: uv run pytest tests/ -v
```

### 주요 개념

| 개념 | 설명 |
|---|---|
| `on` | 트리거 (push, pull_request, schedule 등) |
| `jobs` | 병렬 실행 단위 |
| `steps` | job 내 순차 실행 단위 |
| `runs-on` | 실행 환경 (ubuntu-latest, windows-latest) |
| `uses` | 재사용 가능한 Action |
| `run` | 쉘 명령어 실행 |

---

## ACR + Docker 파이프라인

**Azure Container Registry(ACR)** 에 Docker 이미지를 빌드하고 push합니다.

```yaml
# .github/workflows/docker-build.yml
name: Build and Push to ACR

on:
  push:
    branches: [dev]
    paths:
      - 'adf/custom_activity/**'

jobs:
  build:
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

### ACR 핵심 개념

| 항목 | 설명 |
|---|---|
| **ACR** | Azure에서 제공하는 프라이빗 Docker 레지스트리 |
| **Login Server** | `yourregistry.azurecr.io` 형식 |
| **이미지 태그** | commit SHA를 태그로 사용 → 추적 용이 |
| **GitHub Secrets** | ACR 자격 증명을 안전하게 저장 |

---

## AKS + Terraform (인프라 코드화)

**Azure Kubernetes Service(AKS)** 에 컨테이너를 배포하고,
**Terraform**으로 인프라를 코드로 관리합니다.

### Terraform 기본 구조

```hcl
# main.tf — AKS 클러스터 정의 예시
resource "azurerm_kubernetes_cluster" "aks" {
  name                = "3dt-aks-cluster"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  dns_prefix          = "3dt-aks"

  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_B2s"
  }

  identity {
    type = "SystemAssigned"
  }
}
```

### Terraform 워크플로우

```bash
terraform init      # 프로바이더 초기화
terraform plan      # 변경 사항 미리보기
terraform apply     # 인프라 적용
terraform destroy   # 인프라 삭제
```

### GitHub Actions + Terraform

```yaml
# .github/workflows/infra.yml (간소화)
name: Infrastructure

on:
  push:
    branches: [dev]
    paths: ['infra/**']

jobs:
  terraform:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform plan
      - run: terraform apply -auto-approve
        if: github.ref == 'refs/heads/dev'
```

---

## CI/CD 보안 팁

| 항목 | 방법 |
|---|---|
| 시크릿 관리 | GitHub Secrets 또는 Azure Key Vault |
| 최소 권한 | Service Principal에 필요한 권한만 부여 |
| 이미지 스캔 | ACR에서 취약점 스캔 활성화 |
| 브랜치 보호 | CI 통과 없이 merge 불가 설정 |

---

## 다음 단계

CI/CD를 이해했다면 → [06_automation.md](06_automation.md) 에서 pre-commit 등 개발 자동화를 학습하세요.
