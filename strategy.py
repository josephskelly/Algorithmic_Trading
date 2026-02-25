"""Strategy: compute trade direction and dollar amount."""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

import config

logger = logging.getLogger(__name__)


class TradeDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class TradeDecision:
    """Result of the strategy calculation for a single ETF."""

    symbol: str
    direction: TradeDirection
    dollar_amount: Decimal  # always positive; direction says buy or sell
    pct_change: Decimal


def compute_trade(
    symbol: str,
    pct_change: Decimal,
    net_liq_value: Decimal,
) -> TradeDecision | None:
    """Compute the trade decision for one ETF.

    Returns None if:
    - pct_change is exactly 0 (no move, nothing to do)
    - computed trade amount < MIN_TRADE_SIZE ($5.00)

    Trade Amount = (|pct_change| / 1%) × TRADE_RATE × (NLV / NLV_BASE)
    """
    if pct_change == 0:
        logger.debug("%s: no price change — skip", symbol)
        return None

    abs_pct = abs(pct_change)
    trade_amount = (
        abs_pct / Decimal(1) * Decimal(str(config.TRADE_RATE))
        * (net_liq_value / Decimal(str(config.NLV_BASE)))
    )

    if trade_amount < Decimal(str(config.MIN_TRADE_SIZE)):
        logger.debug(
            "%s: trade amount $%.2f < minimum $%.2f — skip",
            symbol,
            trade_amount,
            config.MIN_TRADE_SIZE,
        )
        return None

    direction = TradeDirection.BUY if pct_change < 0 else TradeDirection.SELL

    logger.info(
        "%s: pct_change=%.2f%%  direction=%s  amount=$%.2f",
        symbol,
        pct_change,
        direction.value,
        trade_amount,
    )

    return TradeDecision(
        symbol=symbol,
        direction=direction,
        dollar_amount=trade_amount,
        pct_change=pct_change,
    )
