#!/usr/bin/env bash
set -euo pipefail

# Download into a caller-selected directory. Existing files are never removed.
# Freqtrade's exchange adapter determines which candle types are actually
# available for the requested historical window.
FREQTRADE_ROOT="${FREQTRADE_ROOT:?Set FREQTRADE_ROOT to an upstream Freqtrade checkout}"
DATA_DIR="${DATA_DIR:?Set DATA_DIR to a separate derivative-data directory}"
TIMERANGE="${TIMERANGE:-20240601-20251202}"
PAIRS="${PAIRS:-BTC/USDT:USDT ETH/USDT:USDT SOL/USDT:USDT XRP/USDT:USDT ADA/USDT:USDT DOGE/USDT:USDT LTC/USDT:USDT}"

mkdir -p "$DATA_DIR"
cd "$FREQTRADE_ROOT"
source .venv/bin/activate

freqtrade download-data \
  --exchange okx \
  --trading-mode futures \
  --pairs $PAIRS \
  --timeframes 1h 4h \
  --candle-types futures mark index funding_rate \
  --timerange "$TIMERANGE" \
  --datadir "$DATA_DIR"

if freqtrade download-data --help 2>&1 | grep -q "open_interest"; then
  echo "Freqtrade advertises open-interest downloads; this checkout may expose it through a separate command." >&2
else
  echo "Open-interest download is not supported by this Freqtrade checkout; no OI values were fabricated." >&2
fi
