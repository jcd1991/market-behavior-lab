# Free crypto market-data supplementation

This project includes `scripts/capture_public_data.py`, a bounded capture
helper for unauthenticated public market feeds. It writes raw JSONL sessions
and a manifest under `user_data/data/microstructure/raw/`, which is ignored by
Git. Install the optional dependency once:

```bash
python -m pip install -e ".[capture]"
```

Capture short sessions:

```bash
python scripts/capture_public_data.py \
  --venue coinbase --pair BTC/USD --pair ETH/USD --seconds 60

python scripts/capture_public_data.py \
  --venue okx --market-type futures \
  --pair BTC/USDT:USDT --seconds 60
```

The collector is read-only and never accepts API keys. Every manifest marks
`execution_truth: false`. Normalize and audit captures before using them to
calibrate an execution model; they are not Freqtrade candle truth.

## Historical fetcher

The companion `scripts/fetch_free_historical.py` writes bounded downloads and
JSON manifests below `user_data/data/historical/raw/`. It supports:

```bash
# Binance global monthly archive with checksum verification
python scripts/fetch_free_historical.py binance \
  --market-type spot --dataset klines --symbol BTCUSDT --interval 1m \
  --month 2026-08 --verify-checksum

# OKX public historical endpoints
python scripts/fetch_free_historical.py okx \
  --dataset history-candles --inst-id BTC-USDT-SWAP --bar 1m --limit 100
python scripts/fetch_free_historical.py okx \
  --dataset funding-rate-history --inst-id BTC-USDT-SWAP --limit 100

# OKX downloadable historical files: module 2 is 1-minute candles;
# modules 4/5 are large L2 archives, so query them before downloading.
python scripts/fetch_free_historical.py okx \
  --dataset market-data-history --module 2 --inst-type SWAP \
  --inst-family-list BTC-USDT --date-aggr-type daily \
  --begin 1788220800000 --end 1788307200000 --download-links

# BitMEX daily public archive
python scripts/fetch_free_historical.py bitmex \
  --dataset trade --date 2015-01-01

# Tardis public first-of-month sample
python scripts/fetch_free_historical.py tardis \
  --exchange deribit --dataset trades --date 2025-03-01 \
  --symbol BTC-PERPETUAL

# Coin Metrics Community coverage catalog
python scripts/fetch_free_historical.py coinmetrics \
  --dataset catalog-market-orderbooks --limit 100
```

Kraken’s official quarterly archive is also supported, but the current full
quarter is roughly 1.3 GB and contains every pair. Use it deliberately rather
than accidentally filling a development disk:

```bash
python scripts/fetch_free_historical.py kraken --quarter 2026Q2
```

The Kraken REST mode is a bounded public page, not a promise of complete
historical retrieval:

```bash
python scripts/fetch_free_historical.py kraken --pair XBTUSD
```

The fetcher fails closed on invalid ZIP/JSON responses, preserves checksums,
and records access failures instead of substituting another venue. Raw files
remain ignored by Git.

## Free sources

| Source | Useful supplementation | Important boundary |
| --- | --- | --- |
| [Coinbase Advanced public WebSocket](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview) | Spot `level2`, `market_trades`, ticker, and candle streams for current Coinbase spread, depth, and trade-flow observations. | Current stream, not a complete historical L2 archive. Track sequence gaps and reconnects. |
| [OKX public WebSocket and REST API](https://www.okx.com/docs-v5/) | Public books, trades, candles, mark price, funding, index, and open-interest endpoints/channels. The public historical-market-data query can return downloadable trades, 1-minute candles, and large L2 files. | Instrument IDs and regional endpoints matter. Historical backfill is still expanding; query availability before downloading. |
| [Binance Public Data](https://github.com/binance/binance-public-data/) | Official global Binance spot/futures 1-minute klines, trades, aggregate trades, and related archives for longer screening windows. | Global Binance is not Binance.US. Audit checksums and documented archive gaps. |
| [Kraken WebSocket API](https://support.kraken.com/articles/360022326871-kraken-websocket-api-frequently-asked-questions) | Public spot book, trade, and OHLC streams as a third-venue current-feed supplement. | WebSocket is current data; historical reconstruction needs REST or a separately permitted archive. |
| [Kraken downloadable trade archive](https://support.kraken.com/in/articles/360047543791-downloadable-historical-market-data-time-and-sales-) | Full public time-and-sales archives by currency pair, distributed as quarterly ZIP files. | The current full quarter is large and includes every pair; the fetcher supports it but does not download it by default. |
| [BitMEX public data](https://public.bitmex.com/) | Daily public trade and quote archives in S3-compatible paths. | Derivatives venue; daily files are not equivalent to full L2 order-book reconstruction. |
| [Deribit API guidance](https://support.deribit.com/hc/en-us/articles/29392445838877-API-guidance) | Public derivatives/options market data for a derivatives-volatility comparison. | Separate derivatives venue, not a substitute for same-venue spot/perpetual carry evidence. |
| [Coin Metrics Community](https://docs.coinmetrics.io/market-data) | Credential-free coverage catalogs and limited normalized market data where the community tier permits it. | Catalog presence does not guarantee data access; per-market requests can return `forbidden`. |
| [Tardis public datasets](https://docs.tardis.dev/downloadable-csv-files) | First-of-month public samples of trades, derivatives ticks, L2, and liquidations. | Broader historical coverage is commercial; preserve the source’s exchange-native format and license boundaries. |
| [CoinGecko API](https://docs.coingecko.com/) | Reference prices, market cap, broad volume, and universe discovery. | Reference-only. Never merge it into Freqtrade execution candles, funding, mark, index, or order-book truth. |

## When free data is not enough

Free public APIs usually provide either a short rolling window or an archive
with incomplete depth, retention, or venue coverage. A paid or licensed archive
may be appropriate for a controlled study. [Tardis documentation](https://docs.tardis.dev/)
describes historical trades, incremental L2, snapshots, quotes, derivatives
ticks, and liquidations across many exchanges; its [downloadable CSV overview](https://docs.tardis.dev/downloadable-csv-files/overview)
is a useful comparison point. Pricing, redistribution rights, and retention
must be verified before procurement or publication.

Coin Metrics Community exposes useful coverage catalogs without credentials,
but actual market-series access is permissioned per market and may return
`forbidden` even when a catalog entry exists. That outcome is recorded as a
coverage limitation, not treated as missing zero-valued data.

The practical order for this project is:

1. Capture Coinbase spot and OKX perpetual current feeds locally.
2. Use Binance Public Data only for clearly labeled global-Binance screening.
3. Add Kraken or Deribit only when a third-venue question requires it.
4. Procure historical event data only for a strategy that survives exact venue
   candles, conservative costs, and walk-forward tests.

## Data-governance rules

- Keep raw captures local; they are ignored by the public repository.
- Preserve venue, instrument, market type, endpoint, UTC receive time, and
  source labels in every normalized artifact.
- Treat receive time as observation time; preserve exchange timestamps when
  the payload provides them.
- Do not fill missing index, mark, funding, open-interest, or liquidation data
  with CoinGecko or another venue.
- Do not mix Binance global, Binance.US, Coinbase, OKX, Kraken, or Deribit
  observations into one unlabeled result.
- Record sequence gaps, reconnects, dropped frames, and archive checksums.
- Never publish credentials or a raw data dump that is not licensed for
  redistribution.

If this makes money, tell me lol. If it loses money, tell me that too—the point
is to measure reality, not promise returns.
