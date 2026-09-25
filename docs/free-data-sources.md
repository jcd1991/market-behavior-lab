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

## Free sources

| Source | Useful supplementation | Important boundary |
| --- | --- | --- |
| [Coinbase Advanced public WebSocket](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview) | Spot `level2`, `market_trades`, ticker, and candle streams for current Coinbase spread, depth, and trade-flow observations. | Current stream, not a complete historical L2 archive. Track sequence gaps and reconnects. |
| [OKX public WebSocket and REST API](https://www.okx.com/docs-v5/) | Public books, trades, candles, mark price, funding, index, and open-interest endpoints/channels for OKX perpetual-futures supplementation. | Instrument IDs and regional endpoints matter. Historical event coverage is not automatically a complete archive. |
| [Binance Public Data](https://github.com/binance/binance-public-data/) | Official global Binance spot/futures 1-minute klines, trades, aggregate trades, and related archives for longer screening windows. | Global Binance is not Binance.US. Audit checksums and documented archive gaps. |
| [Kraken WebSocket API](https://support.kraken.com/articles/360022326871-kraken-websocket-api-frequently-asked-questions) | Public spot book, trade, and OHLC streams as a third-venue current-feed supplement. | WebSocket is current data; historical reconstruction needs REST or a separately permitted archive. |
| [Deribit API guidance](https://support.deribit.com/hc/en-us/articles/29392445838877-API-guidance) | Public derivatives/options market data for a derivatives-volatility comparison. | Separate derivatives venue, not a substitute for same-venue spot/perpetual carry evidence. |
| [CoinGecko API](https://docs.coingecko.com/) | Reference prices, market cap, broad volume, and universe discovery. | Reference-only. Never merge it into Freqtrade execution candles, funding, mark, index, or order-book truth. |

## When free data is not enough

Free public APIs usually provide either a short rolling window or an archive
with incomplete depth, retention, or venue coverage. A paid or licensed archive
may be appropriate for a controlled study. [Tardis documentation](https://docs.tardis.dev/)
describes historical trades, incremental L2, snapshots, quotes, derivatives
ticks, and liquidations across many exchanges; its [downloadable CSV overview](https://docs.tardis.dev/downloadable-csv-files/overview)
is a useful comparison point. Pricing, redistribution rights, and retention
must be verified before procurement or publication.

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
