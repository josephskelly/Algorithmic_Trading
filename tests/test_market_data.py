"""Tests for market_data.py — price fetching and % change computation."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import DXLinkStreamer, MarketData, Quote, Session, Summary

import market_data as md
from market_data import PriceChange


# ---------------------------------------------------------------------------
# Helper: mock get_market_data via side_effect
# ---------------------------------------------------------------------------

def _make_side_effect(data_map: dict[str, MarketData]):
    """Return an async side_effect that looks up MarketData by symbol."""

    async def _side_effect(_session, symbol, _instrument_type):
        if symbol not in data_map:
            raise Exception(f"No data for {symbol}")
        return data_map[symbol]

    return _side_effect


# ---------------------------------------------------------------------------
# DXLink streamer tests (primary path)
# ---------------------------------------------------------------------------

async def test_streamer_primary_path():
    """When the streamer returns data, use it directly (no REST)."""
    streamer_result = {
        "DIG": PriceChange(
            symbol="DIG",
            current_price=Decimal("101"),
            previous_close=Decimal("100"),
            pct_change=Decimal("1"),
        )
    }
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value=streamer_result), \
         patch("market_data._fetch_rest", new_callable=AsyncMock) as mock_rest:
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" in result
    assert result["DIG"].pct_change == Decimal("1")
    mock_rest.assert_not_called()


async def test_no_rest_fallback_when_streamer_partial():
    """When streamer returns data for some symbols, do NOT fall back to REST."""
    streamer_result = {
        "DIG": PriceChange(
            symbol="DIG",
            current_price=Decimal("101"),
            previous_close=Decimal("100"),
            pct_change=Decimal("1"),
        )
    }
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value=streamer_result), \
         patch("market_data._fetch_rest", new_callable=AsyncMock) as mock_rest:
        result = await md.fetch_price_changes(Session(), ["DIG", "ROM"])
    assert "DIG" in result
    assert "ROM" not in result
    mock_rest.assert_not_called()


async def test_fetch_streamer_builds_price_changes():
    """Test _fetch_streamer builds PriceChange from Quote + Summary events."""
    streamer = DXLinkStreamer(Session())
    streamer._quotes = [
        Quote(event_symbol="DIG", bid_price=Decimal("100"), ask_price=Decimal("102")),
    ]
    streamer._summaries = [
        Summary(event_symbol="DIG", prev_day_close_price=Decimal("99")),
    ]

    with patch("market_data.DXLinkStreamer", return_value=streamer):
        result = await md._fetch_streamer(Session(), ["DIG"])

    assert "DIG" in result
    # mid_price = (100 + 102) / 2 = 101, prev_close = 99
    expected_pct = (Decimal("101") - Decimal("99")) / Decimal("99") * 100
    assert result["DIG"].current_price == Decimal("101")
    assert result["DIG"].previous_close == Decimal("99")
    assert result["DIG"].pct_change == expected_pct


async def test_fetch_streamer_skips_incomplete():
    """Streamer skips symbols missing either Quote or Summary."""
    streamer = DXLinkStreamer(Session())
    # Only provide a Quote for DIG, no Summary
    streamer._quotes = [
        Quote(event_symbol="DIG", bid_price=Decimal("100"), ask_price=Decimal("102")),
    ]
    streamer._summaries = []

    with patch("market_data.DXLinkStreamer", return_value=streamer):
        result = await md._fetch_streamer(Session(), ["DIG"])

    assert "DIG" not in result


# ---------------------------------------------------------------------------
# REST endpoint tests (fallback path)
# ---------------------------------------------------------------------------

async def test_rest_fallback_when_streamer_fails():
    """When streamer raises, fall back to REST."""
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, side_effect=Exception("ws fail")), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" in result
    assert result["DIG"].pct_change == Decimal("1")


async def test_rest_fallback_when_streamer_empty():
    """When streamer returns empty dict, fall back to REST."""
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" in result
    assert result["DIG"].pct_change == Decimal("1")


async def test_rest_falls_back_to_mark():
    """REST fallback uses mark price when last is None."""
    data = {"DIG": MarketData(symbol="DIG", last=None, mark=Decimal("102"), prev_close=Decimal("100"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].current_price == Decimal("102")
    assert result["DIG"].pct_change == Decimal("2")


async def test_rest_skips_none_current():
    data = {"DIG": MarketData(symbol="DIG", last=None, mark=None, prev_close=Decimal("100"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_rest_skips_zero_prev_close():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("0"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_rest_skips_none_prev_close():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("50"), mark=Decimal("50"), prev_close=None)}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert "DIG" not in result


async def test_rest_negative_change():
    data = {"DIG": MarketData(symbol="DIG", last=Decimal("95"), mark=Decimal("95"), prev_close=Decimal("100"))}
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result["DIG"].pct_change == Decimal("-5")


async def test_rest_multiple_symbols():
    data = {
        "DIG": MarketData(symbol="DIG", last=Decimal("101"), mark=Decimal("101"), prev_close=Decimal("100")),
        "ROM": MarketData(symbol="ROM", last=Decimal("50"), mark=Decimal("50"), prev_close=Decimal("50")),
        "UYG": MarketData(symbol="UYG", last=Decimal("48"), mark=Decimal("48"), prev_close=Decimal("50")),
    }
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=_make_side_effect(data)):
        result = await md.fetch_price_changes(Session(), ["DIG", "ROM", "UYG"])
    assert len(result) == 3
    assert result["DIG"].pct_change == Decimal("1")
    assert result["ROM"].pct_change == Decimal("0")
    assert result["UYG"].pct_change == Decimal("-4")


# ---------------------------------------------------------------------------
# Both sources fail
# ---------------------------------------------------------------------------

async def test_both_fail():
    """When both streamer and REST fail, return empty dict."""
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, side_effect=Exception("ws fail")), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=Exception("503")):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result == {}


async def test_both_return_empty():
    """When streamer returns empty and REST returns nothing, return empty dict."""
    with patch("market_data._fetch_streamer", new_callable=AsyncMock, return_value={}), \
         patch("market_data.get_market_data", new_callable=AsyncMock, side_effect=Exception("503")):
        result = await md.fetch_price_changes(Session(), ["DIG"])
    assert result == {}
