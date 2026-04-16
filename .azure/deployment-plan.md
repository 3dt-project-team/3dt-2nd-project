# Azure Deployment Plan

> **Status:** Ready for Validation

Generated: 2026-04-16 11:45 KST

---

## 1. Project Overview

**Goal:** Deploy the Flask-based web app under `src/service/web` to Azure App Service and harden the application for App Service runtime behavior.

**Path:** Modernize Existing

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | Development |
| Scale | Small |
| Budget | Balanced |
| **Subscription** | `Data School` (`27db5ec6-d206-4028-b5e1-6004dca5eeef`) |
| **Location** | `koreacentral` (assumed target region for this preparation pass) |

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| Web UI + API | Frontend / API | Flask | `app.py`, `src/service/web` |
| RAG service | API support | Python, Azure OpenAI, PostgreSQL | `src/service/rag` |
| Database access | Data access | SQLAlchemy, psycopg, Key Vault-backed config | `src/utils/database.py`, `src/utils/vault_manager.py` |

---

## 4. Recipe Selection

**Selected:** AZCLI

**Rationale:** The request is to prepare the existing app for Azure App Service and explain the deployment process. App-level hardening plus documented Azure CLI steps are the shortest path without introducing new infra-as-code files unnecessarily.

---

## 5. Architecture

**Stack:** App Service

### Service Mapping

| Component | Azure Service | SKU |
|-----------|---------------|-----|
| Flask web app | Azure App Service (Linux) | Basic B1 or higher |
| Shared compute | Azure App Service Plan (Linux) | Basic B1 |

### Supporting Services

| Service | Purpose |
|---------|---------|
| Application Insights | Request tracing and app monitoring |
| Log Analytics | Centralized logs if workspace-based monitoring is enabled |
| Managed Identity | Key Vault access from App Service |
| Key Vault | Reuse existing secret store already referenced by the app |

---

## 6. Provisioning Limit Checklist

This turn prepares application code and deployment instructions only. Resource creation is not executed in this turn, so quota validation is deferred until the actual provisioning step.

| Resource Type | Number to Deploy | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|-------------|-------|
| `Microsoft.Web/serverfarms` | 1 | 1 | Validate before provisioning | Linux App Service Plan |
| `Microsoft.Web/sites` | 1 | 1 | Validate before provisioning | Python 3.11 web app |
| `Microsoft.Insights/components` | 1 | 1 | Validate before provisioning | Optional but recommended |

**Status:** Deferred for provisioning step

---

## 7. Execution Checklist

### Phase 1: Planning
- [x] Analyze workspace
- [x] Gather requirements from codebase and requested target platform
- [x] Detect runtime entrypoint and dependencies
- [x] Select deployment recipe
- [x] Plan App Service architecture
- [x] Create deployment plan

### Phase 2: Execution
- [x] Add App Service-friendly WSGI entrypoint
- [x] Add reverse-proxy / HTTPS awareness for Flask
- [x] Add lightweight health endpoint
- [x] Fix deployment dependency manifest
- [x] Add startup command/script for Gunicorn
- [x] Document Azure App Service deployment steps

### Phase 3: Validation
- [x] Run focused tests for web routes
- [x] Smoke-check import/startup assumptions

---

## 8. Files to Generate

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment plan and execution tracker | Done |
| `requirements.txt` | App Service build-time dependency install manifest | Done |
| `startup.sh` | Explicit App Service startup command wrapper | Done |
| `docs/app-service-deployment.md` | Operator-facing deployment guide | Done |

---

## 9. Next Steps

> Current: Azure resource creation and platform validation

1. Create the App Service plan and web app in the target resource group and region.
2. Assign managed identity and grant Key Vault secret read access.
3. Configure startup command, app settings, and health check path.
4. Deploy the repository archive and verify `/healthz`, `/`, and `/api/chat`.
