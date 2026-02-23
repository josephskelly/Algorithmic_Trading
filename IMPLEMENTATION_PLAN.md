# Implementation Plan

This document outlines the planned module structure and build order for the algorithmic trading script.

---

## Module Overview

```
Algorithmic_Trading/
├── config.py          # Constants, ETF list loader
├── scheduler.py       # NYSE calendar, close-time detection, daily trigger
├── account.py         # IB connection, account data, order history
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
  - IB host (`127.0.0.1`), port (`7497`), client ID
  - Trade rate: `$165` per `1%` move per `$10,000` of net liquidation value
  - Minimum trade size: `$1.00`

**`scheduler.py`**
- Use `exchange-calendars` library to query the NYSE calendar
- On each trading day:
  - Check if today is a market holiday → skip if so
  - Determine actual close time (regular `4:00 PM ET` or early close `1:00 PM ET`)
  - Calculate trigger time as 5 minutes before actual close
  - Sleep until trigger time, then call the execution callback

---

### Phase 2 — IB connection layer

**`account.py`**
- Connect to TWS/Gateway via `ibapi`
- Fetch net liquidation value via account summary request
- Fetch available cash balance
- Fetch current positions (shares held per ETF symbol)
- Query today's executed and open orders to build the initial traded-today set

---

### Phase 3 — Market data and strategy

**`market_data.py`**
- For a given symbol, fetch current price from IB
- Fetch previous session close price from IB
- Calculate and return `% change = (current - prev_close) / prev_close * 100`

**`strategy.py`**
- Given `% change` and `net liquidation value`, compute:
  ```
  Trade Amount = (|% Change| / 1%) × $165 × (NLV / $10,000)
  ```
- Return `SKIP` if Trade Amount < `$1.00`
- Determine direction: negative % change → BUY; positive % change → SELL
- For BUY: use dollar amount directly (fractional shares via `cashQty`)
- For SELL:
  - If fractional shares supported: use dollar amount
  - If not: floor to nearest whole share; skip if result is `0` shares

---

### Phase 4 — Order management and connection recovery

**`order_manager.py`**
- Place BUY market order using `cashQty` (dollar amount, fractional)
- Place SELL market order (fractional dollar amount or whole share count)
- Maintain traded-today set:
  - Backed by `traded_today.json` (keyed by date) so a script restart preserves state
  - Skip any ETF already in the set for today
- Connection loss handling:
  - Detect via IB error codes `1100`, `1101`, `1102`
  - Retry reconnect up to 3 times with 5-second gaps between attempts
  - If past market close, abort instead of reconnecting
  - After successful reconnect: query IB to rebuild traded-today set; skip any ETF in an ambiguous order state
  - If all reconnect attempts fail: log error and abort for the day

---

### Phase 5 — Orchestration

**`main.py`**
- Wire all modules together in a single daily loop:
  1. Scheduler waits for trigger time (5 min before close)
  2. Query IB for net liquidation value and available cash
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
| Fractional BUY | IB `cashQty` field on market order |
| Fractional SELL | `cashQty` if supported; floor to whole shares if not |
| Reconnect detection | IB error codes `1100` / `1101` / `1102` |
| Traded-today persistence | `traded_today.json` keyed by `YYYY-MM-DD` date |
| Cash guard | Track running cash balance intra-loop; skip if order would go negative |
| Logging | Python `logging` module with daily rotating file handler |
| Paper trading only | Port `7497` (TWS paper) or `4002` (Gateway paper) |

---

## Dependencies (to be added to `requirements.txt`)

- `ibapi` — Interactive Brokers Python API
- `exchange-calendars` — NYSE calendar with early-close support
- `pandas` — CSV loading, date handling

---

## Out of Scope

- No cap on individual trade size (per spec)
- No web UI or dashboard
- No backtesting framework
- No live/real-money account support
