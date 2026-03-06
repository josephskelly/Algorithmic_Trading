"""Market data: fetch prices and compute percentage changes."""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal

from tastytrade import DXLinkStreamer, Session
from tastytrade.dxfeed import Quote, Summary
from tastytrade.market_data import get_market_data, MarketData
from tastytrade.order import InstrumentType

logger = logging.getLogger(__name__)

# Seconds to wait for streamer events before giving up.
_STREAMER_TIMEOUT = 15


@dataclass
class PriceChange:
    """Computed price change for a single ETF."""

    symbol: str
    current_price: Decimal
    previous_close: Decimal
    pct_change: Decimal  # e.g. -1.5 means dropped 1.5%


# ---------------------------------------------------------------------------
# DXLink streamer (primary)
# ---------------------------------------------------------------------------

async def _fetch_streamer(
    session: Session, symbols: list[str]
) -> dict[str, PriceChange]:
    """Fetch quotes + previous close via the DXLink WebSocket streamer.

    Primary data source — streams Quote and Summary events for all symbols
    over a single WebSocket connection.
    Returns a dict of symbol → PriceChange.
    """
    quotes: dict[str, Quote] = {}
    summaries: dict[str, Summary] = {}
    symbol_set = set(symbols)
    needed = len(symbol_set)

    async with DXLinkStreamer(session) as streamer:
        await streamer.subscribe(Quote, symbols)
        await streamer.subscribe(Summary, symbols)

        deadline = asyncio.get_event_loop().time() + _STREAMER_TIMEOUT

        while (len(quotes) < needed or len(summaries) < needed):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break

            # Drain available events from both queues
            for _ in range(needed * 2):
                q = streamer.get_event_nowait(Quote)
                if q is not None and q.event_symbol in symbol_set:
                    quotes[q.event_symbol] = q
                s = streamer.get_event_nowait(Summary)
                if s is not None and s.event_symbol in symbol_set:
                    summaries[s.event_symbol] = s

            if len(quotes) >= needed and len(summaries) >= needed:
                break

            # Brief sleep to let more events arrive
            await asyncio.sleep(0.25)

    results: dict[str, PriceChange] = {}
    for symbol in symbols:
        q = quotes.get(symbol)
        s = summaries.get(symbol)
        if q is None or s is None:
            if q is None and s is None:
                logger.warning("Streamer: %s missing both Quote and Summary — skipping", symbol)
            elif q is None:
                logger.warning("Streamer: %s missing Quote (have Summary) — skipping", symbol)
            else:
                logger.warning("Streamer: %s missing Summary (have Quote) — skipping", symbol)
            continue

        current = q.mid_price
        prev = s.prev_day_close_price

        if current is None or prev is None or prev == 0:
            logger.warning(
                "Streamer: %s missing price data (current=%s, prev_close=%s) — skipping",
                symbol, current, prev,
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
            "Streamer %s: current=%.4f  prev_close=%.4f  pct_change=%.2f%%",
            symbol, current, prev, pct,
        )

    return results


# ---------------------------------------------------------------------------
# REST-based market data (fallback)
# ---------------------------------------------------------------------------

async def _fetch_rest(
    session: Session, symbols: list[str]
) -> dict[str, MarketData]:
    """Fetch market data per symbol via the REST API.

    Returns a dict of symbol → MarketData for every symbol that succeeded.
    """
    data_by_symbol: dict[str, MarketData] = {}
    for symbol in symbols:
        try:
            data = await get_market_data(session, symbol, InstrumentType.EQUITY)
            data_by_symbol[symbol] = data
        except Exception:
            logger.warning("REST market data failed for %s", symbol)
    return data_by_symbol


def _build_price_changes(
    data_by_symbol: dict[str, MarketData],
    symbols: list[str],
) -> dict[str, PriceChange]:
    """Convert REST MarketData objects into PriceChange results."""
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
                symbol, current, prev,
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
            symbol, current, prev, pct,
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_price_changes(
    session: Session, symbols: list[str]
) -> dict[str, PriceChange]:
    """Fetch market data for *symbols* and compute % change from previous close.

    Tries the DXLink WebSocket streamer first.  If it fails or returns
    nothing for all symbols, falls back to the REST market-data endpoint.

    Returns a dict keyed by symbol.  Symbols that lack price data are logged
    and omitted from the result.
    """
    # --- Primary: DXLink streamer ---
    try:
        streamer_results = await _fetch_streamer(session, symbols)
    except Exception as exc:
        logger.warning("DXLink streamer failed: %s — falling back to REST", exc)
        streamer_results = {}

    if streamer_results:
        return streamer_results

    # --- Fallback: REST endpoint ---
    logger.warning(
        "DXLink streamer returned no data for all %d symbols — "
        "falling back to REST endpoint",
        len(symbols),
    )
    data_by_symbol = await _fetch_rest(session, symbols)
    if data_by_symbol:
        return _build_price_changes(data_by_symbol, symbols)

    logger.error("REST fallback also returned no data")
    return {}
