#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -z "${PYTHON_BIN:-}" && -n "${FREQTRADE_ROOT:-}" && -x "$FREQTRADE_ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$FREQTRADE_ROOT/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
"$PYTHON_BIN" -m compileall -q user_data/strategies research tests
"$PYTHON_BIN" -m pytest -q

echo "research checks: PASS"
