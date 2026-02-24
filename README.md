# Algorithmic_Trading
Algorithmic trading script using the tastytrade API on a sandbox (paper trading) account.

## Strategy Overview

Buys 2x leveraged sector ETFs when they drop and sells them when they rise, executing 5 minutes before market close each trading day.

## Flow Chart

```mermaid
flowchart TD
    A([Start]) --> B[Connect to TastyTrade\nSandbox Account]
    B --> C{Connection\nSuccessful?}
    C -- No --> D[Log Error & Exit]
    C -- Yes --> E[Load ETF List from ETFs.csv]

    E --> H[Wait for Next Day\nat Market Open]
    H --> H1{Is Market Open\nToday?\nCheck NYSE Calendar}
    H1 -- No\nHoliday --> H
    H1 -- Yes --> H2[Get Actual Close Time\nRegular: 4:00 PM ET\nEarly Close: 1:00 PM ET]
    H2 --> H3[Wait Until\n5 Min Before Close]

    H3 --> F[Fetch Net Liquidation\nValue from TastyTrade]
    F --> G["Base Rate = $165 × (NLV / $10,000)"]

    G --> I[For Each ETF in List]
    I --> J[Fetch Current Price &\nPrevious Close Price]
    J --> L["% Change = (Current − Prev Close) / Prev Close × 100"]
    L --> M["Trade Amount = (|% Change| / 1%) × Base Rate"]
    M --> M2{"Trade Amount ≥ $5.00?"}
    M2 -- No --> M3[Skip Trade\nLog: Below Minimum] --> S
    M2 -- Yes --> M6{Already Traded\nThis ETF Today?}
    M6 -- Yes --> M7[Skip Trade\nLog: Daily Limit] --> S
    M6 -- No --> N{"% Change < 0?\n(price dropped)"}

    N -- Yes --> BF{is-fractional-\nquantity-eligible?}
    BF -- No --> BFS[Skip Trade\nLog: No Fractional Shares] --> S
    BF -- Yes --> O{Sufficient Cash\nAvailable?}
    O -- No --> P[Skip Trade\nLog: Insufficient Cash] --> S
    O -- Yes --> Q[Place NOTIONAL_MARKET\nBUY for Trade Amount]
    Q --> QCONN{Connection Lost?}
    QCONN -- No --> R[Deduct Trade Amount\nfrom Available Cash] --> S

    N -- No\n(price rose) --> SF{is-fractional-\nquantity-eligible?}
    SF -- Yes --> U{Sufficient Position\nValue ≥ Trade Amount?}
    SF -- No --> FL["Whole Shares = floor(Trade Amount / Price)"]
    FL --> FLC{Whole Shares > 0?}
    FLC -- No --> FLS[Skip Trade\nLog: 0 Shares After Floor] --> S
    FLC -- Yes --> U
    U -- No --> V[Skip Trade\nLog: Insufficient Position] --> S
    U -- Yes --> W[Place NOTIONAL_MARKET\nSELL for Trade Amount]
    W --> WCONN{Connection Lost?}
    WCONN -- No --> X[Update Available Cash] --> S

    S{More ETFs in List?}
    S -- Yes --> I
    S -- No --> Z[Log All Orders Placed] --> H

    QCONN -- Yes --> CREC1
    WCONN -- Yes --> CREC1
    CREC1{Past Market Close?}
    CREC1 -- Yes --> CRECA[Log Error\nAbort for Day] --> H
    CREC1 -- No --> CREC2["Attempt Reconnect\n(up to 3× with 5s gaps)"]
    CREC2 --> CREC3{Reconnect\nSuccessful?}
    CREC3 -- No --> CRECF[Log Error\nAbort for Day] --> H
    CREC3 -- Yes --> CREC4[Query TastyTrade for Today's\nExecuted & Open Orders]
    CREC4 --> CREC5[Rebuild Already-Traded-Today Set]
    CREC5 --> CREC6{Current ETF\nOrder Ambiguous?}
    CREC6 -- Yes --> CREC7[Skip ETF\nLog: Ambiguous State] --> S
    CREC6 -- No --> I
```

## Position Sizing

Trade amount scales linearly with both the % price change and account net liquidation value, queried live from TastyTrade at execution time. Minimum trade size is $5.00.

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
├── account.py         # TastyTrade connection, cash/position queries
├── market_data.py     # Price fetching (current & previous close via DXLink)
├── strategy.py        # % change calculation, trade signal generation
├── order_manager.py   # NOTIONAL_MARKET order placement via tastytrade SDK
├── scheduler.py       # Daily trigger 5 min before market close
└── main.py            # Entry point, orchestration (asyncio event loop)
```

## Setup

### Prerequisites

- Python 3.9+
- A tastytrade sandbox account — register at [developer.tastytrade.com](https://developer.tastytrade.com/sandbox/)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd Algorithmic_Trading
   ```

2. **Install dependencies:**
   ```bash
   pip install tastytrade python-dotenv exchange-calendars pandas
   ```

3. **Configure credentials:**

   Create a `.env` file in the project root:
   ```
   TASTYTRADE_USERNAME=your_sandbox_username
   TASTYTRADE_PASSWORD=your_sandbox_password
   ```
   The script targets the sandbox environment (`api.cert.tastyworks.com`) by default. Never put live account credentials here.

4. **Run the script:**
   ```bash
   python main.py
   ```

### Important Notes

- **Sandbox account only.** This script targets the tastytrade sandbox environment (`api.cert.tastyworks.com`). Do not configure it with live account credentials.
- **The sandbox resets every 24 hours.** All positions, orders, and balances are wiped daily. This is expected behavior for the sandbox environment.
- The script runs continuously and executes the strategy once per day, 5 minutes before the actual market close (typically 3:55 PM ET; adjusted on early-close days).
- Available cash is checked before every buy order. Trades are skipped if cash is insufficient.
- All orders are `NOTIONAL_MARKET` orders (dollar amount) for ETFs that support fractional shares, or whole-share market orders otherwise.
