"""Tests for market_data.py — price fetching and % change computation."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import MarketData, Session

import market_data as md
from market_data import PriceChange


async def test_normal_price_change():
    mock_data = [MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100"))]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" in result
    assert result["DIG"].pct_change == Decimal("1")


async def test_falls_back_to_mark():
    mock_data = [MarketData(symbol="DIG", last=None, mark=Decimal("102"), prev_close=Decimal("100"))]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].current_price == Decimal("102")
    assert result["DIG"].pct_change == Decimal("2")


async def test_skips_missing_symbol():
    # API returns no data for requested symbol
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=[]):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_none_current():
    mock_data = [MarketData(symbol="DIG", last=None, mark=None, prev_close=Decimal("100"))]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_zero_prev_close():
    mock_data = [MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("0"))]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_skips_none_prev_close():
    mock_data = [MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=None)]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_negative_change():
    mock_data = [MarketData(symbol="DIG", last=Decimal("95"), mark=Decimal("95"), prev_close=Decimal("100"))]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].pct_change == Decimal("-5")


async def test_multiple_symbols():
    mock_data = [
        MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100")),
        MarketData(symbol="ROM", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("50")),
        MarketData(symbol="UYG", last=Decimal("48"), mark=Decimal("48"), prev_close=Decimal("50")),
    ]
    with patch("market_data.get_market_data_by_type", new_callable=AsyncMock, return_value=mock_data):
        result = await md.fetch_price_changes(Session(), ["DIG", "ROM", "UYG"])
    assert len(result) == 3
    assert result["DIG"].pct_change == Decimal("1")
    assert result["ROM"].pct_change == Decimal("0")
    assert result["UYG"].pct_change == Decimal("-4")
