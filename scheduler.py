"""Scheduler: NYSE calendar checks and trigger-time calculation."""

import asyncio
import logging
from datetime import datetime, timedelta

import exchange_calendars as xcals
import pandas as pd
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

TRIGGER_OFFSET = timedelta(minutes=5)  # Execute 5 minutes before market close


def _get_nyse_calendar() -> xcals.ExchangeCalendar:
    return xcals.get_calendar("XNYS")


def is_trading_day(date: datetime | None = None) -> bool:
    """Return True if *date* is an NYSE trading session (not a weekend or holiday).

    If *date* is None, uses today in US/Eastern.
    """
    nyse = _get_nyse_calendar()
    if date is None:
        date = datetime.now(ET)
    ts = pd.Timestamp(date.strftime("%Y-%m-%d"))
    return nyse.is_session(ts)


def get_market_close(date: datetime | None = None) -> datetime:
    """Return the market close time for *date* as a US/Eastern datetime.

    Accounts for early closes (e.g. 1:00 PM ET on Christmas Eve).
    Raises ValueError if *date* is not a trading day.
    """
    nyse = _get_nyse_calendar()
    if date is None:
        date = datetime.now(ET)
    ts = pd.Timestamp(date.strftime("%Y-%m-%d"))

    if not nyse.is_session(ts):
        raise ValueError(f"{ts.date()} is not an NYSE trading session")

    close_utc = nyse.schedule.loc[ts, "close"]
    return close_utc.to_pydatetime().replace(tzinfo=UTC).astimezone(ET)


def get_trigger_time(date: datetime | None = None) -> datetime:
    """Return the execution trigger time (5 min before market close) in US/Eastern.

    Raises ValueError if *date* is not a trading day.
    """
    return get_market_close(date) - TRIGGER_OFFSET


async def wait_until_trigger(date: datetime | None = None) -> datetime:
    """Sleep until the trigger time for *date*, then return the trigger time.

    Returns immediately if the trigger time has already passed.
    Raises ValueError if *date* is not a trading day.
    """
    trigger = get_trigger_time(date)
    now = datetime.now(ET)
    wait_seconds = (trigger - now).total_seconds()

    if wait_seconds > 0:
        logger.info("Waiting %.0f seconds until trigger at %s", wait_seconds, trigger.strftime("%H:%M:%S %Z"))
        await asyncio.sleep(wait_seconds)
    else:
        logger.info("Trigger time %s already passed — executing immediately", trigger.strftime("%H:%M:%S %Z"))

    return trigger
