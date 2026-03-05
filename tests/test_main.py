"""Tests for main.py — run_daily orchestration."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zoneinfo import ZoneInfo

from tests.conftest import (
    Account,
    AccountBalance,
    Equity,
    PlacedOrderResponse,
    Session,
    TastytradeError,
)

import main
from market_data import PriceChange
from strategy import TradeDecision, TradeDirection

ET = ZoneInfo("America/New_York")


def _make_session():
    return Session(is_test=True)


def _make_account():
    return Account(account_number="TEST001")


def _make_balances(nlv="50000", cash="25000"):
    return AccountBalance(
        net_liquidating_value=Decimal(nlv),
        cash_balance=Decimal(cash),
    )


def _make_price_changes(symbols, pct=-1.0):
    """Build a dict of PriceChange objects for given symbols."""
    result = {}
    for sym in symbols:
        result[sym] = PriceChange(
            symbol=sym,
            current_price=Decimal("50"),
            previous_close=Decimal("50.50"),
            pct_change=Decimal(str(pct)),
        )
    return result


async def test_run_daily_happy_path(monkeypatch):
    """All ETFs processed when everything succeeds."""
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG", "ROM"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol=s) for s in symbols]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", new_callable=AsyncMock, return_value=price_changes), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, return_value=Decimal("165")) as mock_exec, \
         patch("main.om.mark_traded"):
        await main.run_daily(market_close)
    assert mock_exec.call_count == 2


async def test_skips_already_traded(monkeypatch):
    """ETFs in the traded-today set are skipped."""
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG", "ROM"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol=s) for s in symbols]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", new_callable=AsyncMock, return_value=price_changes), \
         patch("main.om.load_traded_today", return_value={"DIG"}), \
         patch("main.om.execute_trade", new_callable=AsyncMock, return_value=Decimal("165")) as mock_exec, \
         patch("main.om.mark_traded"):
        await main.run_daily(market_close)
    # Only ROM should be traded
    assert mock_exec.call_count == 1


async def test_skips_no_price_data(monkeypatch):
    """ETFs missing from price_changes are skipped."""
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG", "ROM"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol=s) for s in symbols]
    # Only DIG has price data, ROM missing
    price_changes = _make_price_changes(["DIG"])
    balances = _make_balances()

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", new_callable=AsyncMock, return_value=price_changes), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, return_value=Decimal("165")) as mock_exec, \
         patch("main.om.mark_traded"):
        await main.run_daily(market_close)
    assert mock_exec.call_count == 1


async def test_reconnect_on_tastytrade_error(monkeypatch):
    """TastytradeError triggers reconnect flow."""
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol="DIG")]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", new_callable=AsyncMock, return_value=price_changes), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, side_effect=[TastytradeError("fail"), Decimal("165")]) as mock_exec, \
         patch("main.om.reconnect", new_callable=AsyncMock, return_value=_make_session()) as mock_reconnect, \
         patch("main.om.rebuild_traded_set", new_callable=AsyncMock, return_value=set()), \
         patch("main.om.mark_traded"):
        await main.run_daily(market_close)
    mock_reconnect.assert_called_once()


# ===================================================================
# Preflight check
# ===================================================================


async def test_preflight_check_success(monkeypatch):
    """Preflight passes when credentials and account are valid."""
    monkeypatch.setattr("config.TASTYTRADE_PROVIDER_SECRET", "real_secret")
    monkeypatch.setattr("config.TASTYTRADE_REFRESH_TOKEN", "real_token")

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()):
        await main.preflight_check()  # Should not raise


async def test_preflight_check_bad_credentials(monkeypatch):
    """Preflight exits if credentials are empty."""
    monkeypatch.setattr("config.TASTYTRADE_PROVIDER_SECRET", "")
    monkeypatch.setattr("config.TASTYTRADE_REFRESH_TOKEN", "real_token")

    with pytest.raises(SystemExit, match="PROVIDER_SECRET"):
        await main.preflight_check()


async def test_preflight_check_no_account(monkeypatch):
    """Preflight exits if account access fails."""
    monkeypatch.setattr("config.TASTYTRADE_PROVIDER_SECRET", "real_secret")
    monkeypatch.setattr("config.TASTYTRADE_REFRESH_TOKEN", "real_token")

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, side_effect=RuntimeError("No TastyTrade accounts found")):
        with pytest.raises(SystemExit, match="No TastyTrade accounts"):
            await main.preflight_check()


async def test_preflight_check_connection_failure(monkeypatch):
    """Preflight exits if session creation fails."""
    monkeypatch.setattr("config.TASTYTRADE_PROVIDER_SECRET", "real_secret")
    monkeypatch.setattr("config.TASTYTRADE_REFRESH_TOKEN", "real_token")

    with patch("main.acct.create_session", new_callable=AsyncMock, side_effect=Exception("Connection refused")):
        with pytest.raises(SystemExit, match="could not connect"):
            await main.preflight_check()


# ===================================================================
# Run daily
# ===================================================================


async def test_pretrade_retry_succeeds_on_second_attempt(monkeypatch):
    """Market data inner retry handles transient 503 without reconnect."""
    market_close = datetime(2099, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol="DIG")]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    # fetch_price_changes fails on first call (503), succeeds on second
    mock_fetch = AsyncMock(side_effect=[TastytradeError("503"), price_changes])

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", mock_fetch), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, return_value=Decimal("165")) as mock_exec, \
         patch("main.om.mark_traded"), \
         patch("main.om.reconnect", new_callable=AsyncMock, return_value=_make_session()) as mock_reconnect, \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        await main.run_daily(market_close)
    # Trade should still execute after inner retry succeeds
    assert mock_exec.call_count == 1
    # Inner retry handles the 503 — no reconnect needed
    mock_reconnect.assert_not_called()


async def test_market_data_inner_retry_backoff(monkeypatch):
    """Market data inner retry uses exponential backoff delays."""
    market_close = datetime(2099, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol="DIG")]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    # Fail 3 times, then succeed on 4th
    mock_fetch = AsyncMock(side_effect=[
        TastytradeError("503"), TastytradeError("503"),
        TastytradeError("503"), price_changes,
    ])

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", mock_fetch), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, return_value=Decimal("165")) as mock_exec, \
         patch("main.om.mark_traded"), \
         patch("main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await main.run_daily(market_close)

    assert mock_fetch.call_count == 4
    assert mock_exec.call_count == 1
    # Exponential backoff: 5s, 10s, 20s
    sleep_delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert sleep_delays == [5, 10, 20]


async def test_pretrade_retry_all_attempts_fail(monkeypatch):
    """run_daily aborts when all pre-trade fetch attempts fail."""
    market_close = datetime(2099, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG"]
    monkeypatch.setattr("config.ETFS", symbols)

    # All 6 attempts fail
    mock_fetch = AsyncMock(side_effect=TastytradeError("503"))

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=_make_balances()), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=[Equity(symbol="DIG")]), \
         patch("main.md.fetch_price_changes", mock_fetch), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock) as mock_exec, \
         patch("main.om.mark_traded") as mock_mark, \
         patch("main.om.reconnect", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        await main.run_daily(market_close)
    # No trades should execute
    mock_exec.assert_not_called()
    mock_mark.assert_not_called()


async def test_pretrade_retry_aborts_past_market_close(monkeypatch):
    """Pre-trade retry aborts if market close has passed."""
    # Set market_close in the past so the time check triggers
    market_close = datetime(2024, 12, 2, 15, 50, tzinfo=ET)
    symbols = ["DIG"]
    monkeypatch.setattr("config.ETFS", symbols)

    # First attempt fails, then time check should abort
    mock_fetch = AsyncMock(side_effect=TastytradeError("503"))

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=_make_balances()), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=[Equity(symbol="DIG")]), \
         patch("main.md.fetch_price_changes", mock_fetch), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock) as mock_exec, \
         patch("main.om.mark_traded") as mock_mark, \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        await main.run_daily(market_close)
    # Should abort without trading
    mock_exec.assert_not_called()
    mock_mark.assert_not_called()


async def test_abort_on_failed_reconnect(monkeypatch):
    """run_daily returns early when reconnect returns None."""
    market_close = datetime(2024, 12, 2, 16, 0, tzinfo=ET)
    symbols = ["DIG", "ROM"]
    monkeypatch.setattr("config.ETFS", symbols)

    equities = [Equity(symbol=s) for s in symbols]
    price_changes = _make_price_changes(symbols)
    balances = _make_balances()

    with patch("main.acct.create_session", new_callable=AsyncMock, return_value=_make_session()), \
         patch("main.acct.get_account", new_callable=AsyncMock, return_value=_make_account()), \
         patch("main.acct.get_balances", new_callable=AsyncMock, return_value=balances), \
         patch("main.Equity.get", new_callable=AsyncMock, return_value=equities), \
         patch("main.md.fetch_price_changes", new_callable=AsyncMock, return_value=price_changes), \
         patch("main.om.load_traded_today", return_value=set()), \
         patch("main.om.execute_trade", new_callable=AsyncMock, side_effect=TastytradeError("fail")), \
         patch("main.om.reconnect", new_callable=AsyncMock, return_value=None) as mock_reconnect, \
         patch("main.om.mark_traded") as mock_mark:
        await main.run_daily(market_close)
    mock_reconnect.assert_called_once()
    mock_mark.assert_not_called()
