"""Tests for market_data.py — price fetching and % change computation."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import MarketData, Session

import market_data as md
from market_data import PriceChange


def _make_side_effect(data_map: dict[str, MarketData]):
    """Return an async side_effect that looks up MarketData by symbol."""

    async def _side_effect(_session, symbol, _instrument_type):
        if symbol not in data_map:
            raise Exception(f"No data for {symbol}")
        return data_map[symbol]

    return _side_effect


async def test_normal_price_change():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100"))}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" in result
    assert result["DIG"].pct_change == Decimal("1")


async def test_falls_back_to_mark():
    data = {"DIG": MarketData(symbol="DIG", last=None, mark=Decimal("102"), prev_close=Decimal("100"))}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].current_price == Decimal("102")
    assert result["DIG"].pct_change == Decimal("2")


async def test_skips_missing_symbol():
    # get_market_data raises for unknown symbol — fetch_price_changes catches it
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect({})):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_none_current():
    data = {"DIG": MarketData(symbol="DIG", last=None, mark=None, prev_close=Decimal("100"))}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_zero_prev_close():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("0"))}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_none_prev_close():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=None)}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_negative_change():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("95"), mark=Decimal("95"), prev_close=Decimal("100"))}
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].pct_change == Decimal("-5")


async def test_multiple_symbols():
    data = {
        "DIG": MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100")),
        "ROM": MarketData(symbol="ROM", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("50")),
        "UYG": MarketData(symbol="UYG", last=Decimal("48"), mark=Decimal("48"), prev_close=Decimal("50")),
    }
    with patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG", "ROM", "UYG"])
    assert len(result) == 3
    assert result["DIG"].pct_change == Decimal("1")
    assert result["ROM"].pct_change == Decimal("0")
    assert result["UYG"].pct_change == Decimal("-4")
