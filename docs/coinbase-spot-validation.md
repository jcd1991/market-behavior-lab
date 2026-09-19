# Coinbase Advanced spot validation

`RegimeRoutedSpot` is a separate validation lane derived from the regime
detector and long-entry research in `RegimeRouted`. It is not a claim that the
futures strategy transfers to Coinbase.

The lane is deliberately spot-only:

- `can_short = false`;
- leverage is fixed at 1x;
- position adjustments and pyramiding are disabled;
- no funding, mark-price, index-price, or liquidation candles are requested;
- Coinbase pairs use the exact spot form, such as `BTC/USD` and `ETH/USD`.

The example assumes a conservative `0.006` total per-side fee placeholder for
low-volume testing. Replace it with the account's actual Coinbase fee tier
before interpreting results. Coinbase Advanced fees are volume- and
order-type-dependent; maker and taker rates can differ.

## Install and discover

```bash
freqtrade list-strategies \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.coinbase.spot.example.json"
```

## Download public Coinbase candles

```bash
freqtrade download-data \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.coinbase.spot.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --exchange coinbase \
  --pairs BTC/USD ETH/USD SOL/USD XRP/USD \
  --timeframes 1h \
  --timerange 20250101-20260101
```

The public data request does not require credentials. Check the downloaded
pair files and exchange availability before running a longer experiment.
Freqtrade 2026.8 recognizes `coinbase` through CCXT but warns that Coinbase is
not officially supported by the Freqtrade development team; this lane is
therefore an explicit compatibility validation, not a production-support
claim.

## Run the validation backtest

```bash
freqtrade backtesting \
  --userdir "$LAB_ROOT/user_data" \
  --config "$LAB_ROOT/examples/config.backtest.coinbase.spot.example.json" \
  --datadir "$LAB_ROOT/user_data/data" \
  --strategy RegimeRoutedSpot \
  --timerange 20250101-20260101 \
  --export trades
```

Use a rolling walk-forward protocol and compare against buy-and-hold BTC. A
single profitable window is not evidence of a durable edge. Results must be
net of fees, spread, slippage, missing fills, and the actual pair universe.

## Dry-run

The public example has no credentials and keeps the API server disabled. For a
local dry-run, copy it outside the repository, add credentials through secure
environment-backed configuration, and keep `dry_run: true`. Do not publish API
keys or enable live trading as part of this portfolio project.
