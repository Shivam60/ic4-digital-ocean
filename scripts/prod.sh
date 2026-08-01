#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source scripts/lib.sh

ensure_venv requirements.txt
load_env "${ENV_FILE:-deploy/prod.env}"

exec uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "${WEB_CONCURRENCY:-4}" \
    --no-access-log
