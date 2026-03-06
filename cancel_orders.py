"""Cancel all pending LIVE orders in the sandbox account."""

import asyncio
import logging

from tastytrade.order import OrderStatus

import account as acct
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
for name in ("tastytrade", "httpx", "httpcore", "hpack"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def cancel_all() -> None:
    config.validate_credentials()

    session = await acct.create_session()
    account = await acct.get_account(session)

    orders = await acct.get_live_orders(session, account)
    live = [o for o in orders if o.status == OrderStatus.LIVE]

    if not live:
        logger.info("No LIVE orders to cancel.")
        return

    logger.info("Found %d LIVE orders — cancelling...", len(live))
    for order in live:
        try:
            await account.delete_order(session, order.id)
            logger.info("  Cancelled %s %s (order %d)", order.underlying_symbol, order.order_type.value, order.id)
        except Exception as exc:
            logger.error("  Failed to cancel %s (order %d): %s", order.underlying_symbol, order.id, exc)
        await asyncio.sleep(0.5)

    logger.info("Done.")


if __name__ == "__main__":
    asyncio.run(cancel_all())
