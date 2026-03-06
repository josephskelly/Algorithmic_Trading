"""TastyTrade account layer: session management, balances, instruments, orders."""

import logging
from decimal import Decimal
from math import floor

import config
from tastytrade import Session, VERSION as TT_SDK_VERSION
from tastytrade.account import Account, AccountBalance
from tastytrade.instruments import Equity
from tastytrade.market_data import MarketData, get_market_data
from tastytrade.order import (
    InstrumentType,
    Leg,
    NewOrder,
    OrderAction,
    OrderStatus,
    OrderTimeInForce,
    OrderType,
    PlacedOrder,
    PlacedOrderResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

async def create_session() -> Session:
    """Create and return a TastyTrade sandbox session.

    Uses OAuth credentials from config (provider_secret + refresh_token).
    The session auto-refreshes its token on each request.
    """
    session = Session(
        provider_secret=config.TASTYTRADE_PROVIDER_SECRET,
        refresh_token=config.TASTYTRADE_REFRESH_TOKEN,
        is_test=config.SANDBOX,
    )
    # TastyTrade requires User-Agent in <product>/<version> format.
    # The SDK does not set one; missing it can trigger 503 from their proxy.
    session._client.headers["User-Agent"] = (
        f"algorithmic-trading/1.0 tastytrade-sdk/{TT_SDK_VERSION}"
    )
    logger.info("TastyTrade session created (sandbox=%s)", config.SANDBOX)
    return session


# ---------------------------------------------------------------------------
# Account helpers
# ---------------------------------------------------------------------------

async def get_account(session: Session) -> Account:
    """Return the first open account for the authenticated user.

    Raises RuntimeError with an actionable message if no usable account exists.
    """
    accounts = await Account.get(session)
    if accounts:
        account = accounts[0]
        logger.info("Using account %s", account.account_number)
        return account

    # No open accounts — determine why
    all_accounts = await Account.get(session, include_closed=True)
    if all_accounts:
        closed_numbers = [a.account_number for a in all_accounts]
        raise RuntimeError(
            f"All TastyTrade accounts are closed: {closed_numbers}. "
            "Open a new sandbox account at https://developer.tastytrade.com/sandbox/ "
            "or contact TastyTrade support to reactivate."
        )

    raise RuntimeError(
        "No TastyTrade accounts found (open or closed). "
        "This usually means the sandbox account was never fully set up — "
        "you must click 'Add New Account' in the sandbox portal to create a trading account. "
        "Visit https://developer.tastytrade.com/sandbox/ to create one, "
        "then update your .env credentials."
    )


async def get_balances(session: Session, account: Account) -> AccountBalance:
    """Return the current account balances."""
    return await account.get_balances(session)


async def get_net_liquidation_value(session: Session, account: Account) -> Decimal:
    """Return the net liquidation value of the account."""
    balances = await get_balances(session, account)
    return balances.net_liquidating_value


async def get_cash_balance(session: Session, account: Account) -> Decimal:
    """Return the current cash balance of the account."""
    balances = await get_balances(session, account)
    return balances.cash_balance


async def get_positions(session: Session, account: Account) -> dict[str, Decimal]:
    """Return a map of symbol → quantity for all open equity positions."""
    positions = await account.get_positions(session)
    result: dict[str, Decimal] = {}
    for pos in positions:
        if pos.instrument_type == InstrumentType.EQUITY and pos.quantity:
            result[pos.symbol] = pos.quantity
    return result


# ---------------------------------------------------------------------------
# Instrument lookup
# ---------------------------------------------------------------------------

async def is_fractional_eligible(session: Session, symbol: str) -> bool:
    """Check if an ETF supports fractional (notional) orders.

    Returns True if the instrument's is-fractional-quantity-eligible flag is set.
    """
    equity = await Equity.get(session, symbol)
    eligible = equity.is_fractional_quantity_eligible is not False
    logger.debug("%s fractional eligible: %s", symbol, eligible)
    return eligible


# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------

async def get_quote(session: Session, symbol: str) -> MarketData:
    """Return live market data for an equity symbol."""
    return await get_market_data(session, symbol, InstrumentType.EQUITY)


# ---------------------------------------------------------------------------
# Order queries
# ---------------------------------------------------------------------------

async def get_live_orders(session: Session, account: Account) -> list[PlacedOrder]:
    """Return all orders placed today (live orders endpoint)."""
    return await account.get_live_orders(session)


def already_traded_today(orders: list[PlacedOrder], symbol: str) -> bool:
    """Return True if any non-cancelled order exists for *symbol* today."""
    skip_statuses = {OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
    for order in orders:
        if order.underlying_symbol == symbol and order.status not in skip_statuses:
            return True
    return False


# ---------------------------------------------------------------------------
# Order placement
# ---------------------------------------------------------------------------

def _build_leg(symbol: str, action: OrderAction, quantity: Decimal | None = None) -> Leg:
    """Build an equity order leg.

    For notional orders, quantity must be None.
    For share-quantity orders, quantity is the number of shares.
    """
    return Leg(
        instrument_type=InstrumentType.EQUITY,
        symbol=symbol,
        action=action,
        quantity=quantity,
    )


async def place_notional_order(
    session: Session,
    account: Account,
    symbol: str,
    action: OrderAction,
    dollar_amount: Decimal,
    dry_run: bool = False,
) -> PlacedOrderResponse:
    """Place a NOTIONAL_MARKET order for a dollar amount.

    Used for fractional-eligible ETFs (both buys and sells).
    """
    leg = _build_leg(symbol, action, quantity=None)
    # SDK convention: negative value = Debit (buy), positive = Credit (sell)
    signed_value = -dollar_amount if action == OrderAction.BUY_TO_OPEN else dollar_amount
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.NOTIONAL_MARKET,
        legs=[leg],
        value=signed_value,
    )
    logger.info(
        "Placing NOTIONAL_MARKET %s %s $%.2f (dry_run=%s)",
        action.value, symbol, dollar_amount, dry_run,
    )
    return await account.place_order(session, order, dry_run=dry_run)


async def place_share_order(
    session: Session,
    account: Account,
    symbol: str,
    action: OrderAction,
    shares: int,
    dry_run: bool = False,
) -> PlacedOrderResponse:
    """Place a regular MARKET order for a whole number of shares.

    Used for non-fractional-eligible ETFs on sells only.
    """
    leg = _build_leg(symbol, action, quantity=Decimal(shares))
    order = NewOrder(
        time_in_force=OrderTimeInForce.DAY,
        order_type=OrderType.MARKET,
        legs=[leg],
    )
    logger.info(
        "Placing MARKET %s %s %d shares (dry_run=%s)",
        action.value, symbol, shares, dry_run,
    )
    return await account.place_order(session, order, dry_run=dry_run)


def compute_sell_shares(trade_amount: Decimal, current_price: Decimal) -> int:
    """Convert a dollar trade amount to whole shares (floor), for non-fractional sells.

    Returns 0 if the result would be less than 1 share.
    """
    if current_price <= 0:
        return 0
    return floor(trade_amount / current_price)
