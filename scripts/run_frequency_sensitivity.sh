#!/usr/bin/env bash
set -euo pipefail

FREQTRADE_ROOT="${FREQTRADE_ROOT:?Set FREQTRADE_ROOT to an upstream Freqtrade checkout}"
LAB_ROOT="${LAB_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
DATA_DIR="${DATA_DIR:-$LAB_ROOT/user_data/data}"
OUT_DIR="${OUT_DIR:-$LAB_ROOT/research/reports/frequency-sensitivity}"
STRATEGY="${STRATEGY:-RegimeRouted}"
TIMERANGE="${TIMERANGE:-20240613-20251202}"
TIMEFRAMES="${TIMEFRAMES:-1h 4h 1d}"

mkdir -p "$OUT_DIR"
for timeframe in $TIMEFRAMES; do
  target="$OUT_DIR/${STRATEGY}_${timeframe}.zip"
  rm -f "$target"
  "$FREQTRADE_ROOT/.venv/bin/freqtrade" backtesting \
    --userdir "$LAB_ROOT/user_data" \
    --config "$LAB_ROOT/examples/config.backtest.okx.expanded.example.json" \
    --datadir "$DATA_DIR" \
    --strategy "$STRATEGY" \
    --timeframe "$timeframe" \
    --timerange "$TIMERANGE" \
    --export trades \
    --backtest-directory "$OUT_DIR"
  latest="$(find "$OUT_DIR" -maxdepth 1 -type f -name '*.zip' ! -name "$(basename "$target")" -print | xargs -r ls -t | head -n 1)"
  test -n "$latest"
  cp "$latest" "$target"
done

args=()
for timeframe in $TIMEFRAMES; do
  args+=(--run "$timeframe=$OUT_DIR/${STRATEGY}_${timeframe}.zip")
done
"$FREQTRADE_ROOT/.venv/bin/python" -m research.evaluation.frequency_sensitivity \
  --strategy "$STRATEGY" "${args[@]}"
