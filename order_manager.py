"""Order manager: execute trades, track traded-today state, handle reconnects."""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from math import floor
from pathlib import Path

from tastytrade import Session
from tastytrade.account import Account
from tastytrade.order import OrderAction, OrderStatus, PlacedOrder

import account as acct
import config
from market_data import PriceChange
from strategy import TradeDecision, TradeDirection

logger = logging.getLogger(__name__)

TRADED_TODAY_PATH = config.BASE_DIR / "traded_today.json"

RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY_SECONDS = 5


# ---------------------------------------------------------------------------
# Traded-today persistence
# ---------------------------------------------------------------------------

def load_traded_today(date_str: str) -> set[str]:
    """Load the set of symbols already traded on *date_str* from disk."""
    if not TRADED_TODAY_PATH.exists():
        return set()
    try:
        data = json.loads(TRADED_TODAY_PATH.read_text())
        return set(data.get(date_str, []))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read traded_today.json: %s", exc)
        return set()


def save_traded_today(date_str: str, symbols: set[str]) -> None:
    """Persist the traded-today set for *date_str* to disk."""
    data: dict = {}
    if TRADED_TODAY_PATH.exists():
        try:
            data = json.loads(TRADED_TODAY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    data[date_str] = sorted(symbols)
    TRADED_TODAY_PATH.write_text(json.dumps(data, indent=2) + "\n")


def mark_traded(date_str: str, symbol: str, traded: set[str]) -> None:
    """Add *symbol* to the traded set and persist."""
    traded.add(symbol)
    save_traded_today(date_str, traded)


# ---------------------------------------------------------------------------
# Rebuild traded-today from TastyTrade after reconnect
# ---------------------------------------------------------------------------

async def rebuild_traded_set(
    session: Session, account: Account, date_str: str
) -> set[str]:
    """Query TastyTrade for today's orders and rebuild the traded-today set.

    Used after a reconnect to ensure we don't double-trade.
    """
    from datetime import date as date_type

    today = date_type.fromisoformat(date_str)
    skip_statuses = {OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}

    live_orders = await acct.get_live_orders(session, account)
    history = await account.get_order_history(session, start_date=today, end_date=today)

    symbols: set[str] = set()
    for order in live_orders + history:
        if order.status not in skip_statuses:
            symbols.add(order.underlying_symbol)

    logger.info("Rebuilt traded-today set after reconnect: %s", symbols)
    save_traded_today(date_str, symbols)
    return symbols


# ---------------------------------------------------------------------------
# Connection recovery
# ---------------------------------------------------------------------------

async def reconnect(market_close: datetime) -> Session | None:
    """Attempt to reconnect to TastyTrade up to RECONNECT_ATTEMPTS times.

    Returns a new Session on success, or None if all attempts fail or
    reconnecting would push past market close.
    """
    for attempt in range(1, RECONNECT_ATTEMPTS + 1):
        now = datetime.now(market_close.tzinfo)
        if now >= market_close:
            logger.error("Past market close — aborting reconnect")
            return None

        logger.warning("Reconnect attempt %d/%d ...", attempt, RECONNECT_ATTEMPTS)
        try:
            session = await acct.create_session()
            logger.info("Reconnected on attempt %d", attempt)
            return session
        except Exception as exc:
            logger.error("Reconnect attempt %d failed: %s", attempt, exc)
            if attempt < RECONNECT_ATTEMPTS:
                await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    logger.error("All %d reconnect attempts failed — aborting", RECONNECT_ATTEMPTS)
    return None


# ---------------------------------------------------------------------------
# Single-ETF trade execution
# ---------------------------------------------------------------------------

async def execute_trade(
    session: Session,
    account: Account,
    decision: TradeDecision,
    price_info: PriceChange,
    cash_available: Decimal,
    fractional_eligible: bool,
) -> Decimal | None:
    """Execute a single trade based on the strategy decision.

    Returns the dollar amount actually committed (for cash tracking),
    or None if the trade was skipped.
    """
    symbol = decision.symbol
    amount = decision.dollar_amount

    # --- Cash guard (buys only) ---
    if decision.direction == TradeDirection.BUY and amount > cash_available:
        logger.warning(
            "%s: trade amount $%.2f exceeds available cash $%.2f — skip",
            symbol, amount, cash_available,
        )
        return None

    # --- BUY ---
    if decision.direction == TradeDirection.BUY:
        if not fractional_eligible:
            logger.info("%s: not fractional-eligible — skip buy", symbol)
            return None

        await acct.place_notional_order(
            session, account, symbol,
            OrderAction.BUY_TO_OPEN, amount, dry_run=False,
        )
        return amount

    # --- SELL ---
    if fractional_eligible:
        await acct.place_notional_order(
            session, account, symbol,
            OrderAction.SELL_TO_CLOSE, amount, dry_run=False,
        )
        return amount

    # Not fractional-eligible: convert to whole shares
    shares = floor(amount / price_info.current_price)
    if shares <= 0:
        logger.info(
            "%s: trade amount $%.2f → 0 whole shares at $%.2f — skip sell",
            symbol, amount, price_info.current_price,
        )
        return None

    await acct.place_share_order(
        session, account, symbol,
        OrderAction.SELL_TO_CLOSE, shares, dry_run=False,
    )
    return Decimal(shares) * price_info.current_price
