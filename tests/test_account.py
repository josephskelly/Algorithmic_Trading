"""Tests for account.py — pure helpers and async SDK wrappers."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import (
    Account,
    AccountBalance,
    Equity,
    InstrumentType,
    Leg,
    NewOrder,
    OrderAction,
    OrderStatus,
    OrderTimeInForce,
    OrderType,
    PlacedOrder,
    PlacedOrderResponse,
    Session,
)

import account as acct


# ===================================================================
# Pure functions — no mocking needed
# ===================================================================


# --- already_traded_today ---


def test_already_traded_filled():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.FILLED)]
    assert acct.already_traded_today(orders, "DIG") is True


def test_already_traded_not_found():
    orders = [PlacedOrder(underlying_symbol="SPY", status=OrderStatus.FILLED)]
    assert acct.already_traded_today(orders, "DIG") is False


def test_already_traded_cancelled():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.CANCELLED)]
    assert acct.already_traded_today(orders, "DIG") is False


def test_already_traded_rejected():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.REJECTED)]
    assert acct.already_traded_today(orders, "DIG") is False


def test_already_traded_expired():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.EXPIRED)]
    assert acct.already_traded_today(orders, "DIG") is False


def test_already_traded_live():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.LIVE)]
    assert acct.already_traded_today(orders, "DIG") is True


def test_already_traded_received():
    orders = [PlacedOrder(underlying_symbol="DIG", status=OrderStatus.RECEIVED)]
    assert acct.already_traded_today(orders, "DIG") is True


def test_already_traded_empty_list():
    assert acct.already_traded_today([], "DIG") is False


# --- compute_sell_shares ---


def test_compute_sell_shares_exact():
    assert acct.compute_sell_shares(Decimal("100"), Decimal("25")) == 4


def test_compute_sell_shares_floor():
    assert acct.compute_sell_shares(Decimal("99"), Decimal("25")) == 3


def test_compute_sell_shares_zero_price():
    assert acct.compute_sell_shares(Decimal("100"), Decimal("0")) == 0


def test_compute_sell_shares_negative_price():
    assert acct.compute_sell_shares(Decimal("100"), Decimal("-10")) == 0


def test_compute_sell_shares_less_than_one():
    assert acct.compute_sell_shares(Decimal("4"), Decimal("25")) == 0


# --- _build_leg ---


def test_build_leg_notional():
    leg = acct._build_leg("DIG", OrderAction.BUY_TO_OPEN, quantity=None)
    assert leg.instrument_type == InstrumentType.EQUITY
    assert leg.symbol == "DIG"
    assert leg.action == OrderAction.BUY_TO_OPEN
    assert leg.quantity is None


def test_build_leg_shares():
    leg = acct._build_leg("DIG", OrderAction.SELL_TO_CLOSE, quantity=Decimal("5"))
    assert leg.quantity == Decimal("5")
    assert leg.action == OrderAction.SELL_TO_CLOSE


# ===================================================================
# Async functions — mock tastytrade SDK
# ===================================================================


async def test_create_session_sandbox():
    session = await acct.create_session()
    assert session.is_test is True


async def test_create_session_sets_user_agent():
    session = await acct.create_session()
    ua = session._client.headers.get("User-Agent", "")
    assert "algorithmic-trading/" in ua
    assert "tastytrade-sdk/" in ua


async def test_get_account_returns_first():
    session = Session()
    account = await acct.get_account(session)
    assert account.account_number == "SANDBOX123"


async def test_get_account_empty_raises():
    session = Session()
    with patch.object(Account, "get", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(RuntimeError, match="No TastyTrade accounts found"):
            await acct.get_account(session)


async def test_get_account_all_closed():
    """When open accounts is empty but closed accounts exist, error says 'closed'."""
    session = Session()
    closed_account = Account(account_number="CLOSED001")

    async def _mock_get(session, include_closed=False):
        return [] if not include_closed else [closed_account]

    with patch.object(Account, "get", side_effect=_mock_get):
        with pytest.raises(RuntimeError, match="accounts are closed"):
            await acct.get_account(session)


async def test_get_account_none_exist():
    """When no accounts exist at all, error says 'No TastyTrade accounts found'."""
    session = Session()
    with patch.object(Account, "get", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(RuntimeError, match="No TastyTrade accounts found"):
            await acct.get_account(session)


async def test_place_notional_buy_negative_value(mock_session, mock_account):
    """Buy orders should pass a negative signed_value to the SDK."""
    with patch.object(mock_account, "place_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()) as mock_place:
        await acct.place_notional_order(
            mock_session, mock_account, "DIG",
            OrderAction.BUY_TO_OPEN, Decimal("100"), dry_run=False,
        )
        order = mock_place.call_args[0][1]
        assert order.value == Decimal("-100")


async def test_place_notional_sell_positive_value(mock_session, mock_account):
    """Sell orders should pass a positive signed_value to the SDK."""
    with patch.object(mock_account, "place_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()) as mock_place:
        await acct.place_notional_order(
            mock_session, mock_account, "DIG",
            OrderAction.SELL_TO_CLOSE, Decimal("100"), dry_run=False,
        )
        order = mock_place.call_args[0][1]
        assert order.value == Decimal("100")
