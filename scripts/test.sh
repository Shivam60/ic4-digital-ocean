#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

source scripts/lib.sh

ensure_venv requirements-dev.txt

ruff check .
ruff format --check .
pytest "$@"
