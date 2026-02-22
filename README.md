# Algorithmic_Trading
Algorithmic trading script using Interactive Brokers (ibapi) on a paper trading account.

## Strategy Overview

Buys 2x leveraged sector ETFs when they drop and sells them when they rise, executing 5 minutes before market close each trading day.

## Flow Chart

```mermaid
flowchart TD
    A([Start]) --> B[Connect to IB Paper Trading Account]
    B --> C{Connection\nSuccessful?}
    C -- No --> D[Log Error & Exit]
    C -- Yes --> E[Load ETF List from ETFs.csv]
    E --> F[Fetch Net Liquidation Value\nfrom IB Account]
    F --> G["Base Rate = $165 × (Net Liquidation Value / $10,000)"]

    G --> H[Wait for Next Day\nat Market Open]
    H --> H1{Is Market Open\nToday?\nCheck NYSE Calendar}
    H1 -- No\nHoliday --> H
    H1 -- Yes --> H2[Get Actual Close Time\nRegular: 4:00 PM ET\nEarly Close: 1:00 PM ET]
    H2 --> H3[Wait Until\n5 Min Before Close]

    H3 --> I[For Each ETF in List]
    I --> J[Fetch Current Price]
    J --> K[Fetch Previous Close Price]
    K --> L["% Change = (Current − Prev Close) / Prev Close × 100"]
    L --> M["Trade Amount = (|% Change| / 1%) × Base Rate\ne.g. 0.5% drop → buy 0.5 × Base Rate"]
    M --> M2{"Trade Amount\n≥ $1.00?"}
    M2 -- No --> M3[Skip Trade\nLog: Below Minimum]
    M3 --> S
    M2 -- Yes --> M4{Fractional Shares\nSupported?}
    M4 -- No --> M5[Skip Trade\nLog: No Fractional Shares]
    M5 --> S
    M4 -- Yes --> M6{Already Traded\nThis ETF Today?}
    M6 -- Yes --> M7[Skip Trade\nLog: Daily Limit Reached]
    M7 --> S
    M6 -- No --> N{"% Change\n< 0?\n(price dropped)"}
    N -- Yes --> O{Sufficient Cash\nAvailable?}
    O -- No --> P[Skip Trade\nLog: Insufficient Cash]
    O -- Yes --> Q[Place BUY Market Order\nfor Trade Amount]
    Q --> R[Deduct Trade Amount\nfrom Available Cash]
    R --> S{More ETFs\nin List?}
    P --> S

    N -- No --> T{"% Change\n> 0?\n(price rose)"}
    T -- Yes --> U{Sufficient Shares\nOwned?}
    U -- No --> V[Skip Trade\nLog: Insufficient Shares]
    U -- Yes --> W[Place SELL Market Order\nfor Trade Amount]
    W --> X[Update Available Cash]
    X --> S
    V --> S

    T -- No --> Y[No Trade\nPrice Unchanged]
    Y --> S

    S -- Yes --> I
    S -- No --> Z[Log All Orders Placed]
    Z --> H
```

## Position Sizing

Trade amount scales linearly with both the % price change and account net liquidation value, queried live from IB at execution time. Minimum trade size is $1.00.

**Formula:** `Trade Amount = (|% Change| / 1%) × $165 × (Net Liquidation Value / $10,000)`

| % Change | $10,000 NLV | $20,000 NLV | $50,000 NLV |
|---|---|---|---|
| 0.5% | $82.50 | $165.00 | $412.50 |
| 1.0% | $165.00 | $330.00 | $825.00 |
| 2.0% | $330.00 | $660.00 | $1,650.00 |
| 3.5% | $577.50 | $1,155.00 | $2,887.50 |

## ETFs

2x leveraged sector ETFs (see `ETFs.csv` for full list):

| Symbol | Description |
|---|---|
| DIG | Energy |
| LTL | Communication Services |
| ROM | Technology |
| RXL | Health Care |
| UCC | Consumer Discretionary |
| UGE | Consumer Staples |
| UPW | Utilities |
| URE | Real Estate |
| UXI | Industrials |
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
