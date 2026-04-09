# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SENSE** — Semiconductor Economic News & Sentiment Engine. A 6-person team Azure data pipeline: ADF → ADLS Gen2 → Databricks → ML Studio → PostgreSQL.

## Commands

All commands use `uv`. Python version is locked to 3.11.

```bash
# Install dependencies
uv sync                    # base + dev deps
uv sync --extra ml         # adds azure-ai-ml, mlflow
uv sync --extra databricks # adds databricks-sdk

# Run tests
uv run pytest              # all tests
uv run pytest tests/test_vault_manager.py  # single file

# Lint & format
uv run ruff check src/ --fix
uv run ruff format src/

# Type check (alpha — do not use --error-on-warning in CI)
uv run ty check src/

# Pre-commit (run before committing)
uv run pre-commit run --all-files

# Setup (first time)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
cp .env.example .env       # fill in KEY_VAULT_URL
az login                   # required for local dev
uv run python src/utils/vault_manager.py  # verify connection
```

## Architecture

Data flows through four Azure layers:

```
External Sources → ADF (adf/) → ADLS Gen2 (raw/ → curated/ → feature/) → Databricks (notebooks/) → ML Studio (src/models/) → PostgreSQL (sense_db)
```

All credentials are centralized in **Azure Key Vault**, accessed via `DefaultAzureCredential` (local: `az login`, cloud: Managed Identity).

**Key Vault secrets used:**
- `adls-account-name`, `adls-client-id`, `adls-client-secret`, `adls-tenant-id`
- `pg-connection-string`

## Key Modules

**`src/utils/vault_manager.py`** — module-level singleton `vault` object. Import and use directly:
```python
from src.utils.vault_manager import vault

vault.get_secret("my-secret")            # → str | None
vault.get_storage_client()               # → DataLakeServiceClient (or None in Databricks, sets Spark conf)
vault.get_pg_connection()                # → psycopg.Connection
vault.get_pg_connection("sqlalchemy")    # → SQLAlchemy Engine
```
In Databricks, `get_storage_client()` detects the runtime and configures the active `SparkSession` with OAuth instead of returning a client.

**`src/ingestion/yahoo_finance_crawler.py`** — fetches semiconductor stock OHLCV data via `yfinance`, saves CSV locally for manual ADLS Gen2 upload.

**`notebooks/`** — Databricks notebooks as `.py` files: `01_raw_to_curated.py` (cleansing), `02_curated_to_feature.py` (feature engineering).

**`adf/custom_activity/`** — Dockerized Python script for ADF Custom Activity.

## Branch & PR Workflow

**Default branch is `dev`**, not `main`. Never push directly to `dev` or `main`.

Branch naming: `type/short-description` (lowercase, hyphens only)
- Allowed types: `feat`, `fix`, `hotfix`, `chore`, `refactor`, `docs`, `set`

Workflow: Create a GitHub Issue first → branch from `dev` → PR to `dev` → Squash merge → auto-delete branch.

**Commit format:** `type(scope): description` — lowercase, under 50 chars, no trailing period.

| type | 의미 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `hotfix` | 긴급 수정 |
| `chore` | 설정·의존성 변경 |
| `refactor` | 구조 개선 (기능 변화 없음) |
| `docs` | 문서 수정 |

Allowed scopes: `api`, `function`, `pipeline`, `db`, `infra`, `ci`, `auth`, `config`, `guide`

Examples:
```
feat(pipeline): add eventhub trigger
fix(db): correct index on events table
chore(infra): upgrade terraform provider
```

**PR title format:** `[Type] 한국어 설명` or `type(scope): description` both accepted.
(e.g., `[Feat] EventHub 트리거 파이프라인 추가`)

PR body must include: Summary, Changes, Test, Related issue (`Closes #N`).

## Pre-commit Hooks

Two hooks run automatically on every commit:
1. **ruff** — lint + import sort + format (with `--fix` auto-applied)
2. **detect-secrets** — blocks hardcoded secrets (baseline: `.secrets.baseline`)

If `detect-secrets` blocks a false positive, update the baseline with `uv run detect-secrets scan --baseline .secrets.baseline`.

## Tool Configuration

- `ruff`: rules `E, F, I`, line-length 100
- `black`: line-length 100, target py311
- `ty`: checks `src/` directory only

## Data & Security Rules

- Never commit `.csv`, `.parquet`, or other data files
- Never commit `.env` or secrets — use Key Vault
- ADF pipeline JSON lives in `adf/`; coordinate in team chat before editing shared pipelines to avoid JSON merge conflicts
- MLflow experiments must include Git commit hash as a tag for traceability
