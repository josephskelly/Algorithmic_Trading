"""Shared fixtures and tastytrade SDK mock installation.

The tastytrade package is not installed in the test environment. Source modules
import it at the top level (e.g. ``from tastytrade.order import OrderAction``),
so we must install mock modules into ``sys.modules`` BEFORE any source module
is collected by pytest.  This file runs at collection time, making it the right
place for this setup.
"""

import sys
import types
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

import pytest

# ===================================================================
# Mock tastytrade SDK — installed into sys.modules at module level
# ===================================================================

# Create module hierarchy
_tt = types.ModuleType("tastytrade")
_tt_account = types.ModuleType("tastytrade.account")
_tt_instruments = types.ModuleType("tastytrade.instruments")
_tt_market_data = types.ModuleType("tastytrade.market_data")
_tt_order = types.ModuleType("tastytrade.order")
_tt_utils = types.ModuleType("tastytrade.utils")


# --- Enums --------------------------------------------------------
# Values MUST match real SDK; account.py:150 uses enum identity (OrderAction.BUY_TO_OPEN)

class OrderAction(Enum):
    BUY_TO_OPEN = "Buy to Open"
    SELL_TO_CLOSE = "Sell to Close"


class OrderStatus(Enum):
    RECEIVED = "Received"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    LIVE = "Live"


class InstrumentType(Enum):
    EQUITY = "Equity"


class OrderTimeInForce(Enum):
    DAY = "Day"


class OrderType(Enum):
    MARKET = "Market"
    NOTIONAL_MARKET = "Notional Market"


# --- Stub classes -------------------------------------------------

class Session:
    """Stub for tastytrade.Session."""

    def __init__(self, **kwargs):
        self.provider_secret = kwargs.get("provider_secret", "")
        self.refresh_token = kwargs.get("refresh_token", "")
        self.is_test = kwargs.get("is_test", True)
        self._client = types.SimpleNamespace(headers={})


class Account:
    """Stub for tastytrade.account.Account."""

    def __init__(self, account_number="SANDBOX123"):
        self.account_number = account_number

    @classmethod
    async def get(cls, session, include_closed=False):
        return [cls()]

    async def get_balances(self, session):
        return AccountBalance()

    async def get_live_orders(self, session):
        return []

    async def get_order_history(self, session, start_date=None, end_date=None):
        return []

    async def place_order(self, session, order, dry_run=False):
        return PlacedOrderResponse()


@dataclass
class AccountBalance:
    net_liquidating_value: Decimal = Decimal("50000.00")
    cash_balance: Decimal = Decimal("25000.00")


@dataclass
class Equity:
    symbol: str = "SPY"
    is_fractional_quantity_eligible: bool = True

    @classmethod
    async def get(cls, session, symbols):
        if isinstance(symbols, str):
            return cls(symbol=symbols)
        return [cls(symbol=s) for s in symbols]


@dataclass
class MarketData:
    symbol: str = "SPY"
    last: Decimal | None = Decimal("100.00")
    mark: Decimal | None = Decimal("100.00")
    prev_close: Decimal | None = Decimal("99.00")


@dataclass
class Leg:
    instrument_type: InstrumentType = InstrumentType.EQUITY
    symbol: str = "SPY"
    action: OrderAction = OrderAction.BUY_TO_OPEN
    quantity: Decimal | None = None


@dataclass
class NewOrder:
    time_in_force: OrderTimeInForce = OrderTimeInForce.DAY
    order_type: OrderType = OrderType.MARKET
    legs: list = field(default_factory=list)
    value: Decimal | None = None


@dataclass
class PlacedOrder:
    underlying_symbol: str = "SPY"
    status: OrderStatus = OrderStatus.FILLED


@dataclass
class PlacedOrderResponse:
    pass


class TastytradeError(Exception):
    pass


# --- Async helper functions ---------------------------------------

async def _get_market_data(session, symbol, instrument_type):
    return MarketData(symbol=symbol)


async def _get_market_data_by_type(session, equities=None):
    return [MarketData(symbol=s) for s in (equities or [])]


# --- Wire modules into sys.modules --------------------------------

_tt.Session = Session
_tt.VERSION = "0.0.0-test"
sys.modules["tastytrade"] = _tt

_tt_account.Account = Account
_tt_account.AccountBalance = AccountBalance
_tt.account = _tt_account
sys.modules["tastytrade.account"] = _tt_account

_tt_instruments.Equity = Equity
_tt.instruments = _tt_instruments
sys.modules["tastytrade.instruments"] = _tt_instruments

_tt_market_data.MarketData = MarketData
_tt_market_data.get_market_data = _get_market_data
_tt_market_data.get_market_data_by_type = _get_market_data_by_type
_tt.market_data = _tt_market_data
sys.modules["tastytrade.market_data"] = _tt_market_data

_tt_order.InstrumentType = InstrumentType
_tt_order.Leg = Leg
_tt_order.NewOrder = NewOrder
_tt_order.OrderAction = OrderAction
_tt_order.OrderStatus = OrderStatus
_tt_order.OrderTimeInForce = OrderTimeInForce
_tt_order.OrderType = OrderType
_tt_order.PlacedOrder = PlacedOrder
_tt_order.PlacedOrderResponse = PlacedOrderResponse
_tt.order = _tt_order
sys.modules["tastytrade.order"] = _tt_order

_tt_utils.TastytradeError = TastytradeError
_tt.utils = _tt_utils
sys.modules["tastytrade.utils"] = _tt_utils


# ===================================================================
# Shared pytest fixtures
# ===================================================================

@pytest.fixture
def mock_session():
    """A pre-built Session stub."""
    return Session(provider_secret="test_secret", refresh_token="test_token", is_test=True)


@pytest.fixture
def mock_account():
    """A pre-built Account stub."""
    return Account(account_number="TEST001")


@pytest.fixture
def mock_balances():
    """Default account balances."""
    return AccountBalance(
        net_liquidating_value=Decimal("50000.00"),
        cash_balance=Decimal("25000.00"),
    )


@pytest.fixture
def sample_etf_csv(tmp_path):
    """Create a temporary ETFs.csv with known content."""
    csv_content = "Symbol,Description\nSPY,S&P 500\nQQQ,Nasdaq\nDIA,Dow Jones\n"
    csv_file = tmp_path / "ETFs.csv"
    csv_file.write_text(csv_content)
    return csv_file


@pytest.fixture
def patched_traded_path(tmp_path, monkeypatch):
    """Redirect order_manager.TRADED_TODAY_PATH to a tmp_path file."""
    import order_manager
    traded_file = tmp_path / "traded_today.json"
    monkeypatch.setattr(order_manager, "TRADED_TODAY_PATH", traded_file)
    return traded_file
