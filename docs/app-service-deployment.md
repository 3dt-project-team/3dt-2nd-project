# Azure App Service Deployment Guide

## What changed for App Service

- `app.py` now exposes a module-level WSGI app as `app`, which Azure App Service can boot reliably.
- Flask now trusts App Service reverse-proxy headers through `ProxyFix`.
- `/healthz` was added for App Service health checks without touching the database.
- `requirements.txt` was cleaned up for Oryx and `pip install -r requirements.txt`.
- `startup.sh` runs the app with Gunicorn on the port supplied by App Service.

## Recommended target

- OS: Linux
- Runtime stack: Python 3.11
- Plan SKU: Basic B1 or higher

## Required app settings

Set these in App Service Configuration:

- `KEY_VAULT_URL`
- `FLASK_SECRET_KEY`
- `ADMIN_PASSWORD`
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true`
- `ENABLE_ORYX_BUILD=true`

Set these too if you are not resolving them from Key Vault:

- `PG_CONNECTION_STRING`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`

## Azure CLI deployment flow

```bash
az group create --name rg-sense-web --location koreacentral

az appservice plan create \
  --name asp-sense-web \
  --resource-group rg-sense-web \
  --location koreacentral \
  --is-linux \
  --sku B1

az webapp create \
  --name <unique-app-name> \
  --resource-group rg-sense-web \
  --plan asp-sense-web \
  --runtime "PYTHON:3.11"

az webapp identity assign \
  --name <unique-app-name> \
  --resource-group rg-sense-web

az webapp config set \
  --name <unique-app-name> \
  --resource-group rg-sense-web \
  --startup-file "bash startup.sh"

az webapp config appsettings set \
  --name <unique-app-name> \
  --resource-group rg-sense-web \
  --settings \
    KEY_VAULT_URL="https://<your-keyvault>.vault.azure.net/" \
    FLASK_SECRET_KEY="<strong-random-secret>" \
    ADMIN_PASSWORD="<admin-password>" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
    ENABLE_ORYX_BUILD=true
```

## Key Vault access

After assigning the managed identity, grant it permission to read secrets from Key Vault.

- If your Key Vault uses Azure RBAC, assign `Key Vault Secrets User` to the web app's managed identity.
- If your Key Vault uses access policies, add a policy that allows `Get` and `List` on secrets.

## Deploy application code

From the repo root:

```bash
git archive --format zip --output app.zip HEAD

az webapp deploy \
  --resource-group rg-sense-web \
  --name <unique-app-name> \
  --src-path app.zip \
  --type zip
```

## Post-deploy checks

1. Open `https://<unique-app-name>.azurewebsites.net/healthz` and confirm `{"status":"ok","service":"sense-web"}`.
2. Open the root page and confirm the Flask UI loads.
3. Test `POST /api/chat`.
4. Review App Service log stream for startup or import errors.

## Notes

- The root page depends on PostgreSQL access, so `/healthz` is the safer health probe path.
- If Key Vault is unavailable during startup, verify managed identity permissions and `KEY_VAULT_URL`.
- If deployment builds fail, check that `requirements.txt` remains valid and that App Service is using Python 3.11.
