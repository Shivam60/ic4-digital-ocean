#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source scripts/lib.sh

ensure_venv requirements.txt
load_env deploy/demo.env

uvicorn mock_provider.openai:app \
    --host 127.0.0.1 --port "$MOCK_PROVIDER_PORT" --log-level warning &
MOCK_PID=$!
trap 'kill "$MOCK_PID" 2>/dev/null || true' EXIT

wait_for_url "http://127.0.0.1:${MOCK_PROVIDER_PORT}/openapi.json" "mock provider"

echo
echo "Swagger UI   http://127.0.0.1:${PORT}/docs"
echo "Try model   'mock/ok' (also mock/429, mock/500, mock/does-not-exist)"
echo "Primary provider 'dead' is offline on purpose, so replies come from 'mock'."
echo

uvicorn app.main:app --host "$HOST" --port "$PORT"
