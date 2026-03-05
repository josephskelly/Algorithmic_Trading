"""Quick connectivity test for the tastytrade sandbox API.

Usage:
    python test_connectivity.py

Tests each layer of the connection (credentials, session, account, balances)
and reports PASS/FAIL with error details to help diagnose 503 or auth issues.
"""

import asyncio
import sys

import account as acct
import config
from tastytrade.account import Account


def _check_503(exc: Exception) -> None:
    """Print a hint if the error looks like a 503 service outage."""
    msg = str(exc).lower()
    if "503" in msg or ("service" in msg and "unavailable" in msg):
        print("  HINT: 503 typically means the tastytrade sandbox is temporarily down.")
        print("  Wait a few minutes and try again.")
        print("  If persistent, verify User-Agent header is set in account.py.")


async def run_checks() -> bool:
    passed = 0
    total = 4

    # Step 1: Credential validation
    print("[1/4] Checking credentials...")
    try:
        config.validate_credentials()
        print("  PASS — credentials present and not placeholders")
        passed += 1
    except SystemExit as exc:
        print(f"  FAIL — {exc}")
        print("\n=== Aborting: fix credentials before retrying ===")
        return False

    # Step 2: Session creation
    print("[2/4] Creating tastytrade session (sandbox)...")
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
    print("[3/4] Fetching accounts...")
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
    print("[4/4] Fetching account balances...")
    try:
        balances = await account.get_balances(session)
        nlv = balances.net_liquidating_value
        cash = balances.cash_balance
        print(f"  PASS — NLV: ${nlv:,.2f}  |  Cash: ${cash:,.2f}")
        passed += 1
    except Exception as exc:
        print(f"  FAIL — {exc}")
        _check_503(exc)

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
