"""Market data: fetch prices and compute percentage changes."""

import logging
from dataclasses import dataclass
from decimal import Decimal

from tastytrade import Session
from tastytrade.market_data import get_market_data, MarketData
from tastytrade.order import InstrumentType

logger = logging.getLogger(__name__)


@dataclass
class PriceChange:
    """Computed price change for a single ETF."""

    symbol: str
    current_price: Decimal
    previous_close: Decimal
    pct_change: Decimal  # e.g. -1.5 means dropped 1.5%


async def fetch_price_changes(
    session: Session, symbols: list[str]
) -> dict[str, PriceChange]:
    """Fetch market data for each symbol and compute % change from previous close.

    Returns a dict keyed by symbol.  Symbols that lack price data are logged
    and omitted from the result.
    """
    # Fetch individually — the batch /market-data/by-type endpoint returns 503
    # on the sandbox, but the per-symbol endpoint works.
    data_by_symbol: dict[str, MarketData] = {}
    for symbol in symbols:
        try:
            data = await get_market_data(session, symbol, InstrumentType.EQUITY)
            data_by_symbol[symbol] = data
        except Exception:
            logger.warning("Failed to fetch market data for %s — skipping", symbol)

    results: dict[str, PriceChange] = {}

    for symbol in symbols:
        md = data_by_symbol.get(symbol)
        if md is None:
            logger.warning("No market data returned for %s — skipping", symbol)
            continue

        current = md.last if md.last is not None else md.mark
        prev = md.prev_close

        if current is None or prev is None or prev == 0:
            logger.warning(
                "%s missing price data (current=%s, prev_close=%s) — skipping",
                symbol,
                current,
                prev,
            )
            continue

        pct = (current - prev) / prev * 100
        results[symbol] = PriceChange(
            symbol=symbol,
            current_price=current,
            previous_close=prev,
            pct_change=pct,
        )
        logger.debug(
            "%s: current=%.4f  prev_close=%.4f  pct_change=%.2f%%",
            symbol,
            current,
            prev,
            pct,
        )

    return results
