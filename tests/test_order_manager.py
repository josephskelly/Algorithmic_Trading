"""Tests for order_manager.py — persistence, execution, reconnect."""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from zoneinfo import ZoneInfo

from tests.conftest import (
    Account,
    OrderAction,
    OrderStatus,
    PlacedOrder,
    PlacedOrderResponse,
    Session,
)

import order_manager as om
from market_data import PriceChange
from strategy import TradeDecision, TradeDirection

ET = ZoneInfo("America/New_York")


# ===================================================================
# Traded-today persistence (uses patched_traded_path fixture)
# ===================================================================


def test_load_no_file(patched_traded_path):
    result = om.load_traded_today("2024-12-02")
    assert result == set()


def test_load_valid_data(patched_traded_path):
    patched_traded_path.write_text(json.dumps({"2024-12-02": ["DIG", "ROM"]}))
    result = om.load_traded_today("2024-12-02")
    assert result == {"DIG", "ROM"}


def test_load_wrong_date(patched_traded_path):
    patched_traded_path.write_text(json.dumps({"2024-12-01": ["DIG"]}))
    result = om.load_traded_today("2024-12-02")
    assert result == set()


def test_load_corrupt_json(patched_traded_path):
    patched_traded_path.write_text("not valid json{{{")
    result = om.load_traded_today("2024-12-02")
    assert result == set()


def test_save_creates_file(patched_traded_path):
    om.save_traded_today("2024-12-02", {"DIG", "ROM"})
    assert patched_traded_path.exists()
    data = json.loads(patched_traded_path.read_text())
    assert set(data["2024-12-02"]) == {"DIG", "ROM"}


def test_save_preserves_other_dates(patched_traded_path):
    patched_traded_path.write_text(json.dumps({"2024-12-01": ["SPY"]}))
    om.save_traded_today("2024-12-02", {"DIG"})
    data = json.loads(patched_traded_path.read_text())
    assert "2024-12-01" in data
    assert data["2024-12-01"] == ["SPY"]
    assert data["2024-12-02"] == ["DIG"]


def test_mark_traded(patched_traded_path):
    traded = set()
    om.mark_traded("2024-12-02", "DIG", traded)
    assert "DIG" in traded
    data = json.loads(patched_traded_path.read_text())
    assert "DIG" in data["2024-12-02"]


# ===================================================================
# execute_trade (async, mock account module)
# ===================================================================


def _make_decision(direction, amount="165", symbol="DIG"):
    return TradeDecision(
        symbol=symbol,
        direction=direction,
        dollar_amount=Decimal(amount),
        pct_change=Decimal("-1.0") if direction == TradeDirection.BUY else Decimal("1.0"),
    )


def _make_price_info(symbol="DIG", current="50", prev="51"):
    return PriceChange(
        symbol=symbol,
        current_price=Decimal(current),
        previous_close=Decimal(prev),
        pct_change=(Decimal(current) - Decimal(prev)) / Decimal(prev) * 100,
    )


async def test_buy_fractional():
    decision = _make_decision(TradeDirection.BUY, "165")
    price_info = _make_price_info()
    with patch("account.place_notional_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()):
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), True)
    assert result == Decimal("165")


async def test_buy_exceeds_cash():
    decision = _make_decision(TradeDirection.BUY, "500")
    price_info = _make_price_info()
    with patch("account.place_notional_order", new_callable=AsyncMock) as mock_place:
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("100"), True)
    assert result is None
    mock_place.assert_not_called()


async def test_buy_not_fractional():
    # $165 / $50 = 3 whole shares
    decision = _make_decision(TradeDirection.BUY, "165")
    price_info = _make_price_info()
    with patch("account.place_share_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()):
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), False)
    assert result == Decimal("3") * Decimal("50")


async def test_buy_not_fractional_zero_shares():
    # $30 / $50 = 0.6 -> floor = 0 shares -> skip
    decision = _make_decision(TradeDirection.BUY, "30")
    price_info = _make_price_info(current="50")
    with patch("account.place_share_order", new_callable=AsyncMock) as mock_place:
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), False)
    assert result is None
    mock_place.assert_not_called()


async def test_buy_notional_fallback():
    # Notional fails with fractional error -> falls back to whole shares
    decision = _make_decision(TradeDirection.BUY, "165")
    price_info = _make_price_info()
    with patch("account.place_notional_order", new_callable=AsyncMock, side_effect=Exception("fractional_equity_trading_not_supported")), \
         patch("account.place_share_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()) as mock_share:
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), True)
    assert result == Decimal("3") * Decimal("50")
    mock_share.assert_called_once()


async def test_sell_notional_fallback():
    # Notional fails with fractional error -> falls back to whole shares
    decision = _make_decision(TradeDirection.SELL, "150")
    price_info = _make_price_info(current="50")
    with patch("account.place_notional_order", new_callable=AsyncMock, side_effect=Exception("fractional_equity_trading_not_supported")), \
         patch("account.place_share_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()) as mock_share:
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), True)
    assert result == Decimal("3") * Decimal("50")
    mock_share.assert_called_once()


async def test_buy_notional_non_fractional_error_raises():
    # Non-fractional error should still propagate
    decision = _make_decision(TradeDirection.BUY, "165")
    price_info = _make_price_info()
    with patch("account.place_notional_order", new_callable=AsyncMock, side_effect=Exception("network timeout")), \
         pytest.raises(Exception, match="network timeout"):
        await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), True)


async def test_sell_fractional():
    decision = _make_decision(TradeDirection.SELL, "165")
    price_info = _make_price_info()
    with patch("account.place_notional_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()):
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), True)
    assert result == Decimal("165")


async def test_sell_non_frac_whole_shares():
    # $150 / $50 = 3 shares
    decision = _make_decision(TradeDirection.SELL, "150")
    price_info = _make_price_info(current="50")
    with patch("account.place_share_order", new_callable=AsyncMock, return_value=PlacedOrderResponse()):
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), False)
    assert result == Decimal("3") * Decimal("50")


async def test_sell_non_frac_zero_shares():
    # $30 / $50 = 0.6 -> floor = 0 shares -> skip
    decision = _make_decision(TradeDirection.SELL, "30")
    price_info = _make_price_info(current="50")
    with patch("account.place_share_order", new_callable=AsyncMock) as mock_place:
        result = await om.execute_trade(Session(), Account(), decision, price_info, Decimal("10000"), False)
    assert result is None
    mock_place.assert_not_called()


# ===================================================================
# reconnect (async, mock create_session + asyncio.sleep)
# ===================================================================


async def test_reconnect_first_attempt():
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    fake_now = datetime(2024, 12, 2, 15, 56, tzinfo=ET)
    with patch("account.create_session", new_callable=AsyncMock, return_value=Session()), \
         patch("order_manager.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = await om.reconnect(market_close)
    assert result is not None


async def test_reconnect_third_attempt():
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    fake_now = datetime(2024, 12, 2, 15, 56, tzinfo=ET)
    with patch("account.create_session", new_callable=AsyncMock, side_effect=[Exception("fail"), Exception("fail"), Session()]), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("order_manager.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = await om.reconnect(market_close)
    assert result is not None


async def test_reconnect_all_fail():
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    fake_now = datetime(2024, 12, 2, 15, 56, tzinfo=ET)
    with patch("account.create_session", new_callable=AsyncMock, side_effect=Exception("fail")), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("order_manager.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = await om.reconnect(market_close)
    assert result is None


async def test_reconnect_past_close():
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    fake_now = datetime(2024, 12, 2, 16, 5, tzinfo=ET)
    with patch("account.create_session", new_callable=AsyncMock) as mock_create, \
         patch("order_manager.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        result = await om.reconnect(market_close)
    assert result is None
    mock_create.assert_not_called()
