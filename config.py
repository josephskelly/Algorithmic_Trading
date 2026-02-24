"""Configuration: constants and ETF list loader."""

import csv
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
ETF_CSV_PATH = BASE_DIR / "ETFs.csv"

# ---------------------------------------------------------------------------
# TastyTrade credentials & environment
# ---------------------------------------------------------------------------
TASTYTRADE_USERNAME = os.getenv("TASTYTRADE_USERNAME", "")
TASTYTRADE_PASSWORD = os.getenv("TASTYTRADE_PASSWORD", "")
SANDBOX = True  # Always True — we never trade with real money

# ---------------------------------------------------------------------------
# Trade sizing constants
# ---------------------------------------------------------------------------
TRADE_RATE = 165.0       # Dollars per 1% move per $10,000 of net liquidation value
NLV_BASE = 10_000.0      # Denominator for scaling trade size
MIN_TRADE_SIZE = 5.00     # Minimum trade amount in dollars (tastytrade NOTIONAL_MARKET minimum)

# ---------------------------------------------------------------------------
# ETF list loader
# ---------------------------------------------------------------------------

def load_etfs(path: Path = ETF_CSV_PATH) -> list[str]:
    """Load ETF symbols from the CSV file.

    Returns a list of ticker symbols, e.g. ['DIG', 'LTL', ...].
    """
    symbols: list[str] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = row["Symbol"].strip()
            if symbol:
                symbols.append(symbol)
    return symbols


# Pre-load at import time so other modules can just use config.ETFS
ETFS = load_etfs()
