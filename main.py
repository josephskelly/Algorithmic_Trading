"""Main entry point: daily trading loop orchestration."""

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


# ---------------------------------------------------------------------------
# Daily execution
# ---------------------------------------------------------------------------

async def run_daily(market_close: datetime) -> None:
    """Execute the trading strategy for today.

    Called once per trading day at 5 minutes before market close.
    """
    date_str = market_close.strftime("%Y-%m-%d")
    logger.info("=== Trading run for %s ===", date_str)

    # --- Connect ---
    session = await acct.create_session()
    account = await acct.get_account(session)

    # --- Account data ---
    balances = await acct.get_balances(session, account)
    net_liq = balances.net_liquidating_value
    cash_available = balances.cash_balance
    logger.info("Net liquidation value: $%.2f", net_liq)
    logger.info("Cash available: $%.2f", cash_available)

    # --- Traded-today set ---
    traded = om.load_traded_today(date_str)
    if traded:
        logger.info("Already traded today: %s", traded)

    # --- Fractional eligibility (batch lookup) ---
    symbols = config.ETFS
    equities = await Equity.get(session, symbols)
    # Handle single equity (if only one symbol) — normalise to list
    if not isinstance(equities, list):
        equities = [equities]
    eligible_map: dict[str, bool] = {
        eq.symbol: bool(eq.is_fractional_quantity_eligible)
        for eq in equities
    }

    # --- Market data ---
    price_changes = await md.fetch_price_changes(session, symbols)

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
            )
        except TastytradeError as exc:
            logger.error("%s: order failed: %s", symbol, exc)
            # Attempt reconnect
            new_session = await om.reconnect(market_close)
            if new_session is None:
                logger.error("Aborting run — could not reconnect")
                return
            session = new_session
            account = await acct.get_account(session)
            traded = await om.rebuild_traded_set(session, account, date_str)
            if symbol in traded:
                logger.info("%s: confirmed traded after reconnect — skip", symbol)
                continue
            # Retry the trade once after reconnect
            try:
                spent = await om.execute_trade(
                    session, account, decision, pc, cash_available, fractional,
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
            await run_daily(market_close)
        except RuntimeError as exc:
            # Fatal: account/credential issues won't self-resolve overnight
            logger.error("Fatal error in daily run: %s", exc)
            raise SystemExit(f"Aborting: {exc}") from exc
        except Exception as exc:
            logger.error("Daily run failed: %s", exc, exc_info=True)

        # Sleep past close to avoid re-triggering
        await asyncio.sleep(600)


if __name__ == "__main__":
    asyncio.run(main())
