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
TASTYTRADE_PROVIDER_SECRET = os.getenv("TASTYTRADE_PROVIDER_SECRET", "")
TASTYTRADE_REFRESH_TOKEN = os.getenv("TASTYTRADE_REFRESH_TOKEN", "")
SANDBOX = True  # Always True — we never trade with real money
DRY_RUN = False  # Overridden by --dry-run CLI flag


def validate_credentials() -> None:
    """Verify TastyTrade OAuth credentials are present and not placeholders.

    Raises SystemExit with an actionable message if credentials are invalid.
    """
    problems: list[str] = []

    if not TASTYTRADE_PROVIDER_SECRET or TASTYTRADE_PROVIDER_SECRET == "your_oauth_client_secret":
        problems.append(
            "TASTYTRADE_PROVIDER_SECRET is missing or still set to the placeholder value."
        )
    if not TASTYTRADE_REFRESH_TOKEN or TASTYTRADE_REFRESH_TOKEN == "your_refresh_token":
        problems.append(
            "TASTYTRADE_REFRESH_TOKEN is missing or still set to the placeholder value."
        )

    if problems:
        msg = (
            "TastyTrade credential validation failed:\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n\nCopy .env.example to .env and fill in your sandbox OAuth credentials."
            + "\nSee README.md for setup instructions."
        )
        raise SystemExit(msg)


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
