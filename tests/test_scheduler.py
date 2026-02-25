"""Tests for scheduler.py — NYSE calendar and trigger time."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from zoneinfo import ZoneInfo

import scheduler
from scheduler import (
    ET,
    get_market_close,
    get_trigger_time,
    is_trading_day,
    wait_until_trigger,
)

# --- is_trading_day ---


def test_is_trading_day_weekday():
    # 2024-12-02 is a Monday
    dt = datetime(2024, 12, 2, tzinfo=ET)
    assert is_trading_day(dt) is True


def test_is_trading_day_saturday():
    dt = datetime(2024, 12, 7, tzinfo=ET)
    assert is_trading_day(dt) is False


def test_is_trading_day_sunday():
    dt = datetime(2024, 12, 8, tzinfo=ET)
    assert is_trading_day(dt) is False


def test_is_trading_day_holiday():
    # Christmas Day 2024
    dt = datetime(2024, 12, 25, tzinfo=ET)
    assert is_trading_day(dt) is False


# --- get_market_close ---


def test_market_close_regular():
    dt = datetime(2024, 12, 2, tzinfo=ET)
    close = get_market_close(dt)
    assert close.hour == 16
    assert close.minute == 0


def test_market_close_early():
    # 2024-11-29 is Black Friday — NYSE early close at 13:00 ET
    dt = datetime(2024, 11, 29, tzinfo=ET)
    close = get_market_close(dt)
    assert close.hour == 13
    assert close.minute == 0


def test_market_close_non_trading_raises():
    dt = datetime(2024, 12, 7, tzinfo=ET)  # Saturday
    with pytest.raises(ValueError, match="not an NYSE trading session"):
        get_market_close(dt)


# --- get_trigger_time ---


def test_trigger_time_regular():
    dt = datetime(2024, 12, 2, tzinfo=ET)
    trigger = get_trigger_time(dt)
    assert trigger.hour == 15
    assert trigger.minute == 55


# --- wait_until_trigger ---


async def test_wait_until_trigger_already_passed():
    # Mock datetime.now to return a time well after trigger
    past_trigger = datetime(2024, 12, 2, 16, 30, tzinfo=ET)
    with patch("scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = past_trigger
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            trigger = await wait_until_trigger(datetime(2024, 12, 2, tzinfo=ET))
            # Should not have slept or slept with <=0
            if mock_sleep.called:
                assert mock_sleep.call_args[0][0] <= 0
            assert trigger.hour == 15
            assert trigger.minute == 55
