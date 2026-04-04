# 01. Git 기초 (Fundamentals)

## Git이란?

Git은 **분산 버전 관리 시스템(DVCS)** 입니다.
파일의 변경 이력을 추적하고, 여러 사람이 동시에 같은 프로젝트에서 작업할 수 있게 해줍니다.

---

## 3-Area 모델

Git의 핵심은 세 영역(Working Directory → Staging Area → Repository)입니다.

```
Working Directory       Staging Area           Repository (.git)
  (작업 폴더)             (인덱스)               (커밋 히스토리)
       │                     │                        │
       │── git add ──────►   │                        │
       │                     │── git commit ─────►    │
       │◄──────────────── git checkout ───────────────│
```

| 영역 | 설명 |
|---|---|
| **Working Directory** | 실제 파일을 편집하는 로컬 폴더 |
| **Staging Area** | 다음 커밋에 포함할 변경을 선택(인덱싱)하는 중간 영역 |
| **Repository** | `.git/` 디렉토리 안에 저장된 커밋 히스토리 |

---

## 필수 명령어

### 저장소 시작

```bash
# 새 저장소 초기화
git init

# 원격 저장소 복제
git clone <URL>
```

### 변경 추적

```bash
# 현재 상태 확인 (어떤 파일이 수정/추가되었는지)
git status

# 변경 내용 확인 (diff)
git diff                # Working Directory ↔ Staging Area
git diff --staged       # Staging Area ↔ 마지막 커밋
```

### add → commit → push 흐름

```bash
# 1. 변경 파일을 Staging Area에 추가
git add <파일명>        # 특정 파일
git add .              # 현재 디렉토리 전체

# 2. Staging된 변경을 커밋
git commit -m "feat(scope): 설명"

# 3. 원격 저장소에 업로드
git push origin <브랜치명>
```

### 원격 동기화

```bash
# 원격의 변경사항을 로컬로 가져오기 (fetch + merge)
git pull origin <브랜치명>

# fetch만 (merge 없이 확인만)
git fetch origin
```

---

## git pull vs git fetch

| 명령 | 동작 | 사용 시점 |
|---|---|---|
| `git fetch` | 원격 변경사항을 가져오되 **merge하지 않음** | 변경 내용을 먼저 확인하고 싶을 때 |
| `git pull` | `fetch` + `merge` 를 한 번에 수행 | 바로 로컬에 반영하고 싶을 때 |

---

## .gitignore

Git이 추적하지 않을 파일 패턴을 지정합니다.

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/

# 환경 변수 (보안)
.env

# 데이터 파일 (용량)
*.csv
*.parquet
data/
```

> ⚠️ 이미 커밋된 파일은 `.gitignore`에 추가해도 추적이 멈추지 않습니다.
> `git rm --cached <파일>` 로 먼저 추적을 해제해야 합니다.

---

## 설정 (git config)

```bash
# 커밋에 표시될 사용자 정보
git config --global user.name "이름"
git config --global user.email "이메일"

# 기본 브랜치 이름을 main 대신 dev로
git config --global init.defaultBranch dev

# 현재 설정 확인
git config --list
```

---

## 다음 단계

Git 기초를 익혔다면 → [02_branch_strategy.md](02_branch_strategy.md) 에서 브랜치 전략을 학습하세요.
