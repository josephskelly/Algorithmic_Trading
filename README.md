# Algorithmic_Trading
Algorithmic trading script using Interactive Brokers (ibapi) on a paper trading account.

## Strategy Overview

Buys 2x leveraged sector and bond ETFs when they drop and sells them when they rise, executing 5 minutes before market close each trading day.

## Flow Chart

```mermaid
flowchart TD
    A([Start]) --> B[Connect to IB Paper Trading Account]
    B --> C{Connection\nSuccessful?}
    C -- No --> D[Log Error & Exit]
    C -- Yes --> E[Load ETF List from ETFs.csv]
    E --> F[Fetch Account Info\nTotal Deposited Cash]
    F --> G["Calculate Position Size\nX = $165 per $10,000 deposited"]

    G --> H[Wait for Daily Trigger\n5 Minutes Before Market Close]

    H --> I[For Each ETF in List]
    I --> J[Fetch Current Price]
    J --> K[Fetch Previous Close Price]
    K --> L["Calculate % Change\n= (Current - Prev Close) / Prev Close × 100"]

    L --> M{"% Change\n≤ -1%?"}
    M -- Yes --> N["Units to Buy\n= floor(abs(% Change) / 1%)"]
    N --> O["Trade Amount = Units × X"]
    O --> P{Sufficient Cash\nAvailable?}
    P -- No --> Q[Skip Trade\nLog: Insufficient Cash]
    P -- Yes --> R[Place BUY Market Order]
    R --> S[Deduct from Available Cash]
    S --> T{More ETFs\nin List?}
    Q --> T

    M -- No --> U{"% Change\n≥ +1%?"}
    U -- Yes --> V["Units to Sell\n= floor(% Change / 1%)"]
    V --> W["Trade Amount = Units × X"]
    W --> X{Sufficient Shares\nOwned?}
    X -- No --> Y[Skip Trade\nLog: Insufficient Shares]
    X -- Yes --> Z[Place SELL Market Order]
    Z --> AA[Update Available Cash]
    AA --> T
    Y --> T

    U -- No --> AB[No Trade\nPrice Change < 1%]
    AB --> T

    T -- Yes --> I
    T -- No --> AC[Log All Orders Placed]
    AC --> H
```

## Position Sizing

| Total Deposited Cash | Trade Size per 1% Move (X) |
|---|---|
| $10,000 | $165 |
| $20,000 | $330 |
| $50,000 | $825 |
| $100,000 | $1,650 |

**Formula:** `X = (Total Deposited Cash / $10,000) × $165`

## ETFs

2x leveraged sector and bond ETFs (see `ETFs.csv` for full list):

| Symbol | Sector |
|---|---|
| DIG | Oil & Gas |
| LTL | Bonds |
| ROM | Real Estate |
| RXL | Healthcare |
| UBT | Bonds |
| UCC | Consumer |
| UGE | Energy |
| UJB | Bonds |
| UPW | Utilities |
| URE | Real Estate |
| UST | Stocks (Short) |
| UXI | Financials |
| UYG | Financials |
| UYM | Materials |

## Architecture

```
algorithmic_trading/
├── config.py          # Settings, constants, ETF list loader
├── account.py         # IB account connection, cash/position queries
├── market_data.py     # Price fetching (current & previous close)
├── strategy.py        # % change calculation, trade signal generation
├── order_manager.py   # Market order placement via ibapi
├── scheduler.py       # Daily trigger 5 min before market close
└── main.py            # Entry point, orchestration
```

## Setup

### Prerequisites

- Python 3.9+
- Interactive Brokers TWS or IB Gateway (paper trading account)
- `ibapi` Python client

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd Algorithmic_Trading
   ```

2. **Install dependencies:**
   ```bash
   pip install ibapi
   ```

3. **Configure Interactive Brokers:**
   - Open TWS or IB Gateway
   - Log in to your **paper trading** account
   - Enable API connections: *File > Global Configuration > API > Settings*
     - Check "Enable ActiveX and Socket Clients"
     - Set Socket Port to `7497` (paper trading default)
     - Check "Allow connections from localhost only"

4. **Run the script:**
   ```bash
   python main.py
   ```

### Important Notes

- **Paper trading only.** This script is configured exclusively for paper trading accounts (port 7497). Do not connect it to a live account.
- The script runs continuously and executes the strategy once per day, 5 minutes before market close (3:55 PM ET).
- Available cash is checked before every buy order. Trades are skipped if cash is insufficient.
- All orders are market orders executed at the prevailing price.
