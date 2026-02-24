# Implementation Plan

This document outlines the planned module structure and build order for the algorithmic trading script.

---

## Module Overview

```
Algorithmic_Trading/
├── config.py          # Constants, ETF list loader
├── scheduler.py       # NYSE calendar, close-time detection, daily trigger
├── account.py         # TastyTrade connection, account data, order history
├── market_data.py     # Current price, previous close, % change
├── strategy.py        # Trade sizing, direction, fractional share logic
├── order_manager.py   # Order placement, traded-today set, reconnect logic
├── main.py            # Orchestration / daily loop
└── traded_today.json  # Runtime state file (auto-generated, not committed)
```

---

## Build Phases

### Phase 1 — Core scaffolding (no IB connection required)

**`config.py`**
- Load ETF list from `ETFs.csv` into a list of symbols
- Define constants:
  - TastyTrade API base URL and sandbox flag (credentials loaded from `.env`)
  - Trade rate: `$165` per `1%` move per `$10,000` of net liquidation value
  - Minimum trade size: `$5.00`

**`scheduler.py`**
- Use `exchange-calendars` library to query the NYSE calendar
- On each trading day:
  - Check if today is a market holiday → skip if so
  - Determine actual close time (regular `4:00 PM ET` or early close `1:00 PM ET`)
  - Calculate trigger time as 5 minutes before actual close
  - Sleep until trigger time, then call the execution callback

---

### Phase 2 — TastyTrade connection layer

**`account.py`**
- Authenticate with the tastytrade API using credentials from `.env`
  - Sandbox base URL: `api.cert.tastyworks.com`
  - Production base URL: `api.tastyworks.com` (never used by this script)
- Fetch net liquidation value and available cash balance via `account.get_balances(session)`
- Fetch current positions (shares held per ETF symbol) via `account.get_positions(session)`
- Query today's executed and open orders via `account.get_history(session)` to build the initial traded-today set
- All methods are async (`async/await`)

---

### Phase 3 — Market data and strategy

**`market_data.py`**
- Subscribe to the DXLink WebSocket streamer for each ETF symbol
- Fetch current price via `Quote` event (last/mid price)
- Fetch previous session close price via `Summary` event (`prevDayClosePrice` field)
- Calculate and return `% change = (current - prev_close) / prev_close * 100`
- Check `is-fractional-quantity-eligible` for each symbol via the instruments endpoint

**`strategy.py`**
- Given `% change` and `net liquidation value`, compute:
  ```
  Trade Amount = (|% Change| / 1%) × $165 × (NLV / $10,000)
  ```
- Return `SKIP` if Trade Amount < `$5.00`
- Determine direction: negative % change → BUY; positive % change → SELL
- For BUY:
  - If `is-fractional-quantity-eligible`: use `NOTIONAL_MARKET` order for Trade Amount
  - If not: skip trade
- For SELL:
  - If `is-fractional-quantity-eligible`: use `NOTIONAL_MARKET` order for Trade Amount
  - If not: convert to whole shares (`floor(Trade Amount / current price)`); skip if result is `0` shares

---

### Phase 4 — Order management and connection recovery

**`order_manager.py`**
- Place BUY `NOTIONAL_MARKET` order (negative `value` = debit) if `is-fractional-quantity-eligible`; skip otherwise
- Place SELL `NOTIONAL_MARKET` order (positive `value` = credit) if `is-fractional-quantity-eligible`; otherwise place whole-share market order
- Maintain traded-today set:
  - Backed by `traded_today.json` (keyed by date) so a script restart preserves state
  - Skip any ETF already in the set for today
- Connection loss handling:
  - Detect via HTTP errors (5xx, connection timeout) or WebSocket disconnect events
  - Retry reconnect up to 3 times with 5-second gaps between attempts
  - If past market close, abort instead of reconnecting
  - After successful reconnect: query TastyTrade to rebuild traded-today set; skip any ETF in an ambiguous order state
  - If all reconnect attempts fail: log error and abort for the day

---

### Phase 5 — Orchestration

**`main.py`**
- Run inside an `asyncio` event loop (`asyncio.run(main())`)
- Wire all modules together in a single daily loop:
  1. Scheduler waits for trigger time (5 min before close)
  2. Query TastyTrade for net liquidation value and available cash
  3. Load traded-today set from disk
  4. For each ETF in the list (in order):
     - Skip if already in traded-today set
     - Fetch % change via `market_data`
     - Compute trade via `strategy`
     - Skip if Trade Amount < minimum or would overdraw cash
     - Place order via `order_manager`; mark ETF as traded
  5. Log summary for the day

---

## Key Implementation Notes

| Concern | Decision |
|---|---|
| NYSE calendar | `exchange-calendars` library — handles early closes correctly |
| Fractional BUY | `NOTIONAL_MARKET` order (negative `value`) if `is-fractional-quantity-eligible`; else skip |
| Fractional SELL | `NOTIONAL_MARKET` order (positive `value`) if `is-fractional-quantity-eligible`; else floor to whole shares |
| Reconnect detection | HTTP errors (5xx, timeout) or WebSocket disconnect events |
| Traded-today persistence | `traded_today.json` keyed by `YYYY-MM-DD` date |
| Cash guard | Track running cash balance intra-loop; skip if order would go negative |
| Logging | Python `logging` module with daily rotating file handler |
| Paper trading only | Sandbox environment (`api.cert.tastyworks.com`); resets daily |

---

## Dependencies (to be added to `requirements.txt`)

- `tastytrade` — tastytrade Python SDK (async REST + DXLink WebSocket)
- `python-dotenv` — load API credentials from `.env` file
- `exchange-calendars` — NYSE calendar with early-close support
- `pandas` — CSV loading, date handling

---

## Out of Scope

- No cap on individual trade size (per spec)
- No web UI or dashboard
- No backtesting framework
- No live/real-money account support
