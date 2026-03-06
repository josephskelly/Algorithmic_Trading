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
    WCONN -- No --> X[Log Trade Executed] --> S

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
Algorithmic_Trading/
├── main.py            # Entry point — asyncio event loop, daily orchestration
├── config.py          # Constants, ETF list loader, credentials from .env
├── scheduler.py       # NYSE calendar, close-time detection, trigger timing
├── account.py         # TastyTrade session, balances, order placement
├── market_data.py     # Batch price fetching, % change computation
├── strategy.py        # Trade sizing, direction (buy on drops, sell on rises)
├── order_manager.py   # Traded-today tracking, connection recovery, execution
├── ETFs.csv           # List of 2x leveraged sector ETFs
├── requirements.txt   # Python dependencies
├── .env.example       # Credential template (copy to .env)
└── traded_today.json  # Runtime state (auto-generated, not committed)
```

## Setup

### Prerequisites

- Python 3.11+
- A tastytrade developer account and sandbox (paper trading) credentials

### Step 1: Clone the repository

```bash
git clone <repo-url>
cd Algorithmic_Trading
```

### Step 2: Create a virtual environment (recommended)

```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Set up tastytrade OAuth credentials

The script uses OAuth2 authentication with the tastytrade API. You need a **provider secret** (client secret) and a **refresh token**.

1. **Create a sandbox account** at [developer.tastytrade.com/sandbox/](https://developer.tastytrade.com/sandbox/)
2. **Create a trading account** — after signing in to the sandbox portal, click **"Add New Account"** to create a paper trading account. Without this step, OAuth will succeed but there will be no trading account to use and the script will fail with "No TastyTrade accounts found."
3. **Create an OAuth application** at the developer portal
   - Set the callback URL to `http://localhost:8000`
4. **Save the client secret** (provider secret) generated during app creation
5. **Create a grant** (refresh token) from the OAuth Applications section
6. **Copy `.env.example` to `.env`** and fill in both values:

```bash
cp .env.example .env
```

Edit `.env`:
```
TASTYTRADE_PROVIDER_SECRET=your_oauth_client_secret
TASTYTRADE_REFRESH_TOKEN=your_refresh_token
```

Refresh tokens never expire, so this is a one-time setup.

### Step 5: Run the script

```bash
python main.py
```

The script runs continuously:
- On each trading day, it waits until 5 minutes before market close
- Executes the strategy for all ETFs in `ETFs.csv`
- Sleeps until the next trading day

### On-Demand Execution (Testing)

You can trigger the strategy immediately without waiting for the scheduled time:

```bash
# Execute now and place real sandbox orders
python main.py --now

# Execute now but only validate orders (no placement)
python main.py --now --dry-run
```

| Flag | Effect |
|---|---|
| `--now` | Bypass the scheduler and execute immediately. Works on any day including weekends and holidays. Ignores the traded-today guard so you can run repeatedly. |
| `--dry-run` | Orders are validated by tastytrade but not placed. Can be used with or without `--now`. |

On non-trading days (weekends/holidays), market data may not be available from tastytrade — the script will log warnings and skip ETFs with no price data.

### Important Notes

- **Sandbox account only.** The `SANDBOX = True` flag in `config.py` ensures the script always connects to `api.cert.tastyworks.com`. Never change this to `False` or use live account credentials.
- The script handles early-close days automatically (e.g., Christmas Eve at 1:00 PM ET).
- If the connection drops during execution, the script retries up to 3 times with 5-second gaps. After reconnecting, it rebuilds the traded-today set from TastyTrade to avoid duplicate orders.
- All orders use `NOTIONAL_MARKET` (dollar-amount) orders for ETFs that support fractional shares. For non-eligible ETFs, buys are skipped and sells are floored to whole shares.
- **Sells require a position.** The script queries open positions at the start of each run. If you don't hold shares of an ETF, sell signals are skipped. Sell amounts are also capped to the value of shares actually held, preventing over-selling.
- Sell proceeds settle T+1 and are **not** available for same-day buys. The cash guard only tracks same-day buy spend.
- The `traded_today.json` file persists the list of ETFs already traded each day, so the script can safely restart without double-trading.
- Logs are printed to stdout. Redirect to a file for persistent logging:
  ```bash
  python main.py >> trading.log 2>&1
  ```

## Google Cloud Deployment

To run the script continuously without relying on a personal machine, deploy it to a Google Cloud Compute Engine VM. The `e2-micro` instance type is included in Google Cloud's [free tier](https://cloud.google.com/free) (one per billing account in eligible US regions).

### Prerequisites

- A Google Cloud account with billing enabled (free tier is sufficient)
- The [`gcloud` CLI](https://cloud.google.com/sdk/docs/install) installed on your local machine
- Authenticate and select a project:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 1. Create the VM

```bash
gcloud compute instances create algo-trading \
    --zone=us-east1-b \
    --machine-type=e2-micro \
    --image-family=debian-12 \
    --image-project=debian-cloud \
    --boot-disk-size=10GB \
    --boot-disk-type=pd-standard
```

`us-east1-b` is recommended since the script operates on Eastern Time (NYSE hours). The `e2-micro` instance (2 shared vCPUs, 1 GB memory) is more than sufficient — the script sleeps most of the time.

### 2. Connect to the VM

```bash
gcloud compute ssh algo-trading --zone=us-east1-b
```

The first connection will generate SSH keys automatically.

### 3. Install system dependencies

Run on the VM:

```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

### 4. Clone and set up the project

```bash
cd /opt
sudo git clone <repo-url> algo-trading
sudo chown -R $USER:$USER /opt/algo-trading
cd /opt/algo-trading
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5. Configure credentials

```bash
cp .env.example .env
nano .env
```

Fill in `TASTYTRADE_PROVIDER_SECRET` and `TASTYTRADE_REFRESH_TOKEN` with your sandbox credentials (see [Step 4](#step-4-set-up-tastytrade-oauth-credentials) above for how to obtain these).

Restrict file permissions since the file contains credentials:

```bash
chmod 600 .env
```

### 6. Create a systemd service

This configures the script to start on boot, restart on failure, and capture logs via `journalctl`.

Create the service file (replace `YOUR_USERNAME` with the output of `whoami`):

```bash
sudo tee /etc/systemd/system/algo-trading.service << 'EOF'
[Unit]
Description=Algorithmic Trading Script (tastytrade sandbox)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/opt/algo-trading
ExecStart=/opt/algo-trading/venv/bin/python main.py
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable algo-trading
sudo systemctl start algo-trading
```

### 7. Verify it is running

```bash
sudo systemctl status algo-trading
```

The output should show `active (running)`. Check the live logs:

```bash
sudo journalctl -u algo-trading -f
```

You should see startup messages followed by either "Not a trading day -- sleeping until tomorrow" or "Waiting N seconds until trigger at HH:MM:SS ET".

### 8. Useful commands

| Command | Purpose |
|---|---|
| `sudo systemctl status algo-trading` | Check if the service is running |
| `sudo journalctl -u algo-trading -f` | Follow live logs |
| `sudo journalctl -u algo-trading --since today` | View today's logs |
| `sudo journalctl -u algo-trading --since "2026-03-02"` | View logs from a specific date |
| `sudo systemctl restart algo-trading` | Restart the service |
| `sudo systemctl stop algo-trading` | Stop the service |
| `sudo systemctl start algo-trading` | Start the service |

### 9. Updating the script

When you pull new code, reinstall dependencies and restart the service:

```bash
cd /opt/algo-trading
source venv/bin/activate
git pull
pip install -r requirements.txt
sudo systemctl restart algo-trading
```

### Cost

The `e2-micro` instance is included in Google Cloud's free tier (one per billing account in `us-east1`, `us-central1`, or `us-west1`). Beyond the free tier, it costs approximately $6–8/month. The script uses negligible CPU and network bandwidth since it sleeps most of the time.
