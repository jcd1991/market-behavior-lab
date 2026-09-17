#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m compileall -q user_data/strategies research tests
"$PYTHON_BIN" -m pytest -q

echo "research checks: PASS"
