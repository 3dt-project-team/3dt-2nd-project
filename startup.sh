#!/bin/bash
set -euo pipefail

PORT="${PORT:-8000}"

exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --timeout 600 \
  --access-logfile "-" \
  --error-logfile "-" \
  app:app
