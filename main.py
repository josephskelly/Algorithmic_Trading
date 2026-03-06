"""Main entry point: daily trading loop orchestration."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta

from tastytrade.instruments import Equity
from tastytrade.utils import TastytradeError

import account as acct
import config
import market_data as md
import order_manager as om
import scheduler
from strategy import TradeDirection, compute_trade

PRETRADE_FETCH_ATTEMPTS = 6
MARKET_DATA_ATTEMPTS = 6

# Order-rejection error substrings — reconnecting won't help with these.
_ORDER_REJECTION_KEYWORDS = [
    "order_unavailable",
    "insufficient",
    "not_allowed",
    "invalid",
    "rejected",
]


def _is_order_rejection(exc: TastytradeError) -> bool:
    """Return True if the error is an order validation rejection, not a connection issue."""
    msg = str(exc).lower()
    return any(kw in msg for kw in _ORDER_REJECTION_KEYWORDS)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
logging.getLogger("tastytrade").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Daily execution
# ---------------------------------------------------------------------------

async def run_daily(
    market_close: datetime,
    dry_run: bool = False,
    skip_traded_today: bool = False,
) -> None:
    """Execute the trading strategy for today.

    Called once per trading day at 5 minutes before market close.
    When *dry_run* is True, orders are validated but not placed.
    When *skip_traded_today* is True, the traded-today guard is bypassed.
    """
    date_str = market_close.strftime("%Y-%m-%d")
    logger.info("=== Trading run for %s ===", date_str)
    if dry_run:
        logger.info("DRY RUN MODE — orders will be validated but not placed")

    # --- Connect + fetch pre-trade data (with retry) ---
    session = None
    for attempt in range(1, PRETRADE_FETCH_ATTEMPTS + 1):
        try:
            if session is None:
                session = await acct.create_session()
            account = await acct.get_account(session)

            # Account data
            balances = await acct.get_balances(session, account)
            net_liq = balances.net_liquidating_value
            cash_available = balances.cash_balance
            logger.info("Net liquidation value: $%.2f", net_liq)
            logger.info("Cash available: $%.2f", cash_available)

            # Current positions (for sell guards)
            positions = await acct.get_positions(session, account)
            if positions:
                logger.info("Open positions: %s", {s: float(q) for s, q in positions.items()})

            # Fractional eligibility (batch lookup)
            symbols = config.ETFS
            equities = await Equity.get(session, symbols)
            if not isinstance(equities, list):
                equities = [equities]
            eligible_map: dict[str, bool] = {
                eq.symbol: eq.is_fractional_quantity_eligible is not False
                for eq in equities
            }
            ineligible = [s for s, e in eligible_map.items() if not e]
            if ineligible:
                logger.info("ETFs not fractional-eligible: %s", ineligible)

            # Market data (separate retry with exponential backoff)
            price_changes = None
            md_delay = 5
            for md_attempt in range(1, MARKET_DATA_ATTEMPTS + 1):
                try:
                    price_changes = await md.fetch_price_changes(session, symbols)
                    break
                except Exception as md_exc:
                    logger.warning(
                        "Market data fetch failed (attempt %d/%d): %s",
                        md_attempt, MARKET_DATA_ATTEMPTS, md_exc,
                    )
                    if md_attempt == MARKET_DATA_ATTEMPTS:
                        raise  # Let outer loop handle final failure
                    now_md = datetime.now(market_close.tzinfo)
                    if now_md >= market_close:
                        raise  # Let outer loop handle close-time abort
                    await asyncio.sleep(md_delay)
                    md_delay = min(md_delay * 2, 60)  # 5s, 10s, 20s, 40s, 60s

            break  # All pre-trade data fetched successfully
        except Exception as exc:
            logger.error(
                "Pre-trade data fetch failed (attempt %d/%d): %s",
                attempt, PRETRADE_FETCH_ATTEMPTS, exc,
            )
            if attempt == PRETRADE_FETCH_ATTEMPTS:
                logger.error("All pre-trade fetch attempts failed — aborting run")
                return
            now = datetime.now(market_close.tzinfo)
            if now >= market_close:
                logger.error("Past market close — aborting run")
                return
            await asyncio.sleep(om.RECONNECT_DELAY_SECONDS)
            session = await om.reconnect(market_close)
            if session is None:
                logger.error("Reconnect failed — aborting run")
                return

    # --- Traded-today set ---
    if skip_traded_today:
        traded: set[str] = set()
        logger.info("Traded-today guard bypassed (on-demand mode)")
    else:
        traded = om.load_traded_today(date_str)
        if traded:
            logger.info("Already traded today: %s", traded)

    # --- Process each ETF ---
    for symbol in symbols:
        if symbol in traded:
            logger.info("%s: already traded today — skip", symbol)
            continue

        pc = price_changes.get(symbol)
        if pc is None:
            logger.warning("%s: no price data — skip", symbol)
            continue

        decision = compute_trade(symbol, pc.pct_change, net_liq)
        if decision is None:
            continue

        fractional = eligible_map.get(symbol, False)

        try:
            spent = await om.execute_trade(
                session, account, decision, pc, cash_available, fractional,
                positions, dry_run=dry_run,
            )
        except TastytradeError as exc:
            logger.error("%s: order failed: %s", symbol, exc)
            if _is_order_rejection(exc):
                logger.warning("%s: order rejected (not a connection issue) — skip", symbol)
                continue
            # Connection-related error — attempt reconnect
            new_session = await om.reconnect(market_close)
            if new_session is None:
                logger.error("Aborting run — could not reconnect")
                return
            session = new_session
            try:
                account = await acct.get_account(session)
                traded = await om.rebuild_traded_set(session, account, date_str)
            except Exception as rebuild_exc:
                logger.error(
                    "Post-reconnect rebuild failed: %s — aborting run", rebuild_exc
                )
                return
            if symbol in traded:
                logger.info("%s: confirmed traded after reconnect — skip", symbol)
                continue
            # Retry the trade once after reconnect
            try:
                spent = await om.execute_trade(
                    session, account, decision, pc, cash_available, fractional,
                    positions, dry_run=dry_run,
                )
            except Exception as retry_exc:
                logger.error("%s: retry failed after reconnect: %s — skip", symbol, retry_exc)
                continue
        except Exception as exc:
            logger.error("%s: unexpected error: %s — skip", symbol, exc)
            continue

        if spent is not None:
            om.mark_traded(date_str, symbol, traded)
            if decision.direction == TradeDirection.BUY:
                cash_available -= spent
            logger.info(
                "%s: trade executed ($%.2f)  cash remaining: $%.2f",
                symbol, spent, cash_available,
            )

    logger.info("=== Trading run complete for %s ===", date_str)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

async def preflight_check() -> None:
    """Validate credentials and account access at startup.

    Exits the process immediately if any check fails, so problems are
    caught before waiting hours for the trigger time.
    """
    logger.info("Running startup preflight checks...")

    # 1. Credential validation (exits on failure)
    config.validate_credentials()
    logger.info("  Credentials present")

    # 2. Session + account access
    try:
        session = await acct.create_session()
        account = await acct.get_account(session)
        logger.info("  Account access verified: %s", account.account_number)
    except RuntimeError as exc:
        logger.error("Preflight check failed: %s", exc)
        raise SystemExit(f"Startup aborted: {exc}") from exc
    except Exception as exc:
        logger.error("Preflight check failed (unexpected): %s", exc)
        raise SystemExit(
            f"Startup aborted — could not connect to TastyTrade: {exc}"
        ) from exc

    logger.info("Preflight checks passed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    """Main loop: wait for each trading day's trigger, then execute."""
    logger.info("Algorithmic trading script started")
    logger.info("ETFs: %s", config.ETFS)
    logger.info("Sandbox mode: %s", config.SANDBOX)

    # --- Fail fast: verify credentials and account before entering the loop ---
    await preflight_check()

    while True:
        now = datetime.now(scheduler.ET)

        # Helper: sleep until tomorrow 00:01 ET then re-evaluate
        async def _sleep_until_tomorrow() -> None:
            t = now.replace(hour=0, minute=1, second=0, microsecond=0) + timedelta(days=1)
            await asyncio.sleep((t - now).total_seconds())

        if not scheduler.is_trading_day(now):
            logger.info("Not a trading day — sleeping until tomorrow")
            await _sleep_until_tomorrow()
            continue

        try:
            market_close = scheduler.get_market_close(now)
        except ValueError:
            logger.info("Could not get market close — sleeping until tomorrow")
            await _sleep_until_tomorrow()
            continue

        # If market already closed, skip to tomorrow
        if now > market_close:
            logger.info("Market already closed — sleeping until tomorrow")
            await _sleep_until_tomorrow()
            continue

        # Wait for trigger (5 min before close)
        await scheduler.wait_until_trigger(now)

        # Execute
        try:
            await run_daily(market_close, dry_run=config.DRY_RUN)
        except RuntimeError as exc:
            # Fatal: account/credential issues won't self-resolve overnight
            logger.error("Fatal error in daily run: %s", exc)
            raise SystemExit(f"Aborting: {exc}") from exc
        except Exception as exc:
            logger.error("Daily run failed: %s", exc, exc_info=True)

        # Sleep past close to avoid re-triggering
        await asyncio.sleep(600)


async def run_now(dry_run: bool = False) -> None:
    """Execute the strategy immediately, bypassing the scheduler.

    Used for on-demand testing in sandbox mode.  Ignores the traded-today
    guard so the run can be repeated without clearing state.
    """
    logger.info("On-demand execution requested")
    await preflight_check()

    now = datetime.now(scheduler.ET)

    # Use real close time on trading days; synthetic close on non-trading days
    # so the reconnect guard doesn't interfere.
    if scheduler.is_trading_day(now):
        try:
            market_close = scheduler.get_market_close(now)
        except ValueError:
            market_close = now + timedelta(minutes=10)
    else:
        market_close = now + timedelta(minutes=10)
        logger.info("Not a trading day — using synthetic market close")

    await run_daily(market_close, dry_run=dry_run, skip_traded_today=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Algorithmic trading strategy (sandbox only)",
    )
    parser.add_argument(
        "--now", action="store_true",
        help="Execute immediately, skip scheduler",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate orders without placing them",
    )
    args = parser.parse_args()

    if args.now:
        asyncio.run(run_now(dry_run=args.dry_run))
    else:
        config.DRY_RUN = args.dry_run
        asyncio.run(main())
