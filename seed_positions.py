"""Seed initial positions: buy all ETFs assuming a 1% drop."""

import argparse
import asyncio
import logging
from decimal import Decimal

from tastytrade.instruments import Equity

import account as acct
import config
import market_data as md
import order_manager as om
from strategy import compute_trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Suppress noisy SDK/httpx DEBUG logs
for name in ("tastytrade", "httpx", "httpcore", "hpack"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

ORDER_DELAY = 1  # seconds between orders to avoid rate limiting
SIMULATED_PCT_CHANGE = Decimal("-1.0")  # assume 1% drop → triggers buys


async def seed(dry_run: bool = False) -> None:
    config.validate_credentials()

    session = await acct.create_session()
    account = await acct.get_account(session)

    balances = await acct.get_balances(session, account)
    net_liq = balances.net_liquidating_value
    cash_available = balances.cash_balance
    logger.info("Net liquidation value: $%.2f", net_liq)
    logger.info("Cash available: $%.2f", cash_available)

    if dry_run:
        logger.info("DRY RUN MODE — orders will be validated but not placed")

    symbols = config.ETFS

    # Fractional eligibility
    equities = await Equity.get(session, symbols)
    if not isinstance(equities, list):
        equities = [equities]
    eligible_map = {
        eq.symbol: eq.is_fractional_quantity_eligible is not False
        for eq in equities
    }

    # Live prices (needed for whole-share fallback)
    price_changes = await md.fetch_price_changes(session, symbols)

    for symbol in symbols:
        pc = price_changes.get(symbol)
        if pc is None:
            logger.warning("%s: no price data — skip", symbol)
            continue

        decision = compute_trade(symbol, SIMULATED_PCT_CHANGE, net_liq)
        if decision is None:
            continue

        if decision.dollar_amount > cash_available:
            logger.warning(
                "%s: $%.2f exceeds available cash $%.2f — skip",
                symbol, decision.dollar_amount, cash_available,
            )
            continue

        fractional = eligible_map.get(symbol, False)
        try:
            spent = await om.execute_trade(
                session, account, decision, pc, cash_available, fractional,
                positions={}, dry_run=dry_run,
            )
        except Exception as exc:
            logger.error("%s: order failed: %s — skip", symbol, exc)
            continue

        if spent is not None:
            cash_available -= spent
            logger.info(
                "%s: bought $%.2f  cash remaining: $%.2f",
                symbol, spent, cash_available,
            )
            await asyncio.sleep(ORDER_DELAY)

    logger.info("Seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial ETF positions")
    parser.add_argument("--dry-run", action="store_true", help="Validate orders without placing")
    args = parser.parse_args()
    asyncio.run(seed(dry_run=args.dry_run))
