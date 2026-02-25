"""Tests for strategy.py — trade sizing logic (highest priority).

Formula: Trade Amount = |pct_change| × TRADE_RATE × (NLV / NLV_BASE)
"""

from decimal import Decimal

from strategy import TradeDecision, TradeDirection, compute_trade


# --- Direction ---

def test_buy_on_price_drop():
    result = compute_trade("DIG", Decimal("-1.0"), Decimal("10000"))
    assert result is not None
    assert result.direction == TradeDirection.BUY


def test_sell_on_price_rise():
    result = compute_trade("DIG", Decimal("1.0"), Decimal("10000"))
    assert result is not None
    assert result.direction == TradeDirection.SELL


# --- Zero change ---

def test_zero_change_returns_none():
    assert compute_trade("DIG", Decimal("0"), Decimal("10000")) is None


def test_zero_change_decimal_zero():
    assert compute_trade("DIG", Decimal("0.0"), Decimal("10000")) is None


# --- Minimum trade size ($5.00) ---

def test_below_minimum_returns_none():
    # 0.001 * 165 * 1.0 = $0.165 < $5.00
    assert compute_trade("DIG", Decimal("0.001"), Decimal("10000")) is None


def test_exactly_minimum_threshold():
    # pct_change such that amount == $5.00 exactly: 5/165 * 165 * 1 = 5.00
    pct = Decimal("5") / Decimal("165")
    result = compute_trade("DIG", -pct, Decimal("10000"))
    assert result is not None
    assert result.dollar_amount == Decimal("5.00") or result.dollar_amount >= Decimal("5")


def test_just_below_minimum():
    # 4.99/165 * 165 * 1.0 = $4.99 < $5.00
    pct = Decimal("4.99") / Decimal("165")
    assert compute_trade("DIG", -pct, Decimal("10000")) is None


# --- Dollar amount calculation ---

def test_1pct_drop_10k():
    result = compute_trade("DIG", Decimal("-1.0"), Decimal("10000"))
    assert result.dollar_amount == Decimal("165")


def test_1pct_drop_20k():
    result = compute_trade("DIG", Decimal("-1.0"), Decimal("20000"))
    assert result.dollar_amount == Decimal("330")


def test_half_pct_drop_10k():
    result = compute_trade("DIG", Decimal("-0.5"), Decimal("10000"))
    assert result.dollar_amount == Decimal("82.5")


def test_2pct_rise_10k():
    result = compute_trade("DIG", Decimal("2.0"), Decimal("10000"))
    assert result.dollar_amount == Decimal("330")
    assert result.direction == TradeDirection.SELL


def test_5pct_drop_50k():
    result = compute_trade("DIG", Decimal("-5.0"), Decimal("50000"))
    # 5.0 * 165 * 5.0 = $4125
    assert result.dollar_amount == Decimal("4125")
    assert result.direction == TradeDirection.BUY


def test_small_nlv():
    result = compute_trade("DIG", Decimal("-1.0"), Decimal("1000"))
    # 1.0 * 165 * 0.1 = $16.50
    assert result.dollar_amount == Decimal("16.5")


# --- Decimal precision ---

def test_decimal_precision():
    result = compute_trade("DIG", Decimal("0.1"), Decimal("10000"))
    # 0.1 * 165 * 1.0 = $16.5 exactly
    assert result.dollar_amount == Decimal("16.5")
    assert isinstance(result.dollar_amount, Decimal)


# --- Output fields ---

def test_output_fields():
    result = compute_trade("ROM", Decimal("-2.5"), Decimal("10000"))
    assert result.symbol == "ROM"
    assert result.direction == TradeDirection.BUY
    assert result.pct_change == Decimal("-2.5")
    # 2.5 * 165 * 1.0 = $412.50
    assert result.dollar_amount == Decimal("412.5")
