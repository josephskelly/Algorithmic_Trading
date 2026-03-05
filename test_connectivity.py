"""Quick connectivity test for the tastytrade sandbox API.

Usage:
    python test_connectivity.py

Tests each layer of the connection (credentials, session, account, balances,
market data) and reports PASS/FAIL with error details to help diagnose issues.
"""

import asyncio
import sys

import account as acct
import config
from tastytrade.account import Account
from tastytrade.market_data import get_market_data
from tastytrade.order import InstrumentType


def _check_503(exc: Exception) -> None:
    """Print a hint if the error looks like a 503 service outage."""
    msg = str(exc).lower()
    if "503" in msg or ("service" in msg and "unavailable" in msg):
        print("  HINT: 503 typically means the tastytrade sandbox is temporarily down.")
        print("  Wait a few minutes and try again.")
        print("  If persistent, verify User-Agent header is set in account.py.")


async def run_checks() -> bool:
    passed = 0
    total = 5

    # Step 1: Credential validation
    print("[1/5] Checking credentials...")
    try:
        config.validate_credentials()
        print("  PASS — credentials present and not placeholders")
        passed += 1
    except SystemExit as exc:
        print(f"  FAIL — {exc}")
        print("\n=== Aborting: fix credentials before retrying ===")
        return False

    # Step 2: Session creation
    print("[2/5] Creating tastytrade session (sandbox)...")
    try:
        session = await acct.create_session()
        print("  PASS — session created")
        passed += 1
    except Exception as exc:
        print(f"  FAIL — {exc}")
        _check_503(exc)
        print("\n=== Aborting: session creation failed ===")
        return False

    # Step 3: Account access
    print("[3/5] Fetching accounts...")
    try:
        accounts = await Account.get(session)
        if not accounts:
            print("  FAIL — no accounts returned (sandbox account may need setup)")
            print("  Visit https://developer.tastytrade.com/sandbox/ to create one.")
            print("\n=== Aborting: no accounts found ===")
            return False
        account = accounts[0]
        print(f"  PASS — account {account.account_number}")
        passed += 1
    except Exception as exc:
        print(f"  FAIL — {exc}")
        _check_503(exc)
        print("\n=== Aborting: account fetch failed ===")
        return False

    # Step 4: Account balances
    print("[4/5] Fetching account balances...")
    try:
        balances = await account.get_balances(session)
        nlv = balances.net_liquidating_value
        cash = balances.cash_balance
        print(f"  PASS — NLV: ${nlv:,.2f}  |  Cash: ${cash:,.2f}")
        passed += 1
    except Exception as exc:
        print(f"  FAIL — {exc}")
        _check_503(exc)

    # Step 5: Market data availability
    print("[5/5] Testing market data...")
    control_symbols = ["SPY", "VOO", "QQQ"]
    etf_symbols = config.ETFS
    all_ok = True

    # Test control symbols first (common ETFs that should always have data)
    print("  --- Control symbols ---")
    for symbol in control_symbols:
        try:
            data = await get_market_data(session, symbol, InstrumentType.EQUITY)
            last = getattr(data, "last", None)
            prev = getattr(data, "prev_close", None)
            print(f"  {symbol:6s} PASS  last={last}  prev_close={prev}")
        except Exception as exc:
            print(f"  {symbol:6s} FAIL  {exc}")
            all_ok = False

    # Test configured ETFs
    print("  --- Configured ETFs ---")
    etf_ok = 0
    for symbol in etf_symbols:
        try:
            data = await get_market_data(session, symbol, InstrumentType.EQUITY)
            last = getattr(data, "last", None)
            prev = getattr(data, "prev_close", None)
            print(f"  {symbol:6s} PASS  last={last}  prev_close={prev}")
            etf_ok += 1
        except Exception:
            print(f"  {symbol:6s} FAIL  no market data")
            all_ok = False

    if all_ok:
        print(f"  PASS — all symbols have market data")
        passed += 1
    elif etf_ok == 0:
        print(f"  FAIL — none of the {len(etf_symbols)} configured ETFs have market data")
        print("  HINT: The sandbox may not have data for 2x leveraged ETFs.")
        print("  The DXLink streamer fallback will be used at runtime.")
    else:
        print(f"  PARTIAL — {etf_ok}/{len(etf_symbols)} ETFs have market data")
        passed += 1  # Count partial as pass since some work

    # Summary
    print()
    if passed == total:
        print(f"=== ALL {total} CHECKS PASSED — connectivity OK ===")
        return True
    else:
        print(f"=== {passed}/{total} checks passed ===")
        return False


if __name__ == "__main__":
    print("tastytrade sandbox connectivity test")
    print("=" * 40)
    ok = asyncio.run(run_checks())
    sys.exit(0 if ok else 1)
