#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if rg -n -i "private[[:space:]]*[-—][[:space:]]*do not redistribute|/Applications/MAMP/htdocs/freqtrade|dry_run[[:space:]]*:[[:space:]]*false|api[_-]?key[[:space:]]*[:=]" \
  README.md docs examples user_data/strategies research; then
  echo "public repository validation failed: forbidden marker, local path, live flag, or key reference found" >&2
  exit 1
fi

if find . -type f \( -name '*.sqlite' -o -name '*.sqlite3' -o -name '*.db' -o -name '*.whl' \) -print -quit | rg .; then
  echo "public repository validation failed: generated database or binary found" >&2
  exit 1
fi

echo "public repository validation: PASS"
