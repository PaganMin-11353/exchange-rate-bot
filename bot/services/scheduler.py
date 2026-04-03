"""Scheduled jobs for fetching and storing exchange rates."""

import logging

from bot import database
from bot.services.exchange_api import get_rate

logger = logging.getLogger(__name__)


async def fetch_and_store_rates(context) -> None:
    """Job callback: fetch latest rates for all active base currencies.

    Called by JobQueue every RATE_FETCH_INTERVAL_SECONDS.
    One fetch per distinct base currency (not per pair) to minimize API calls.
    """
    bases = database.get_distinct_base_currencies()
    if not bases:
        logger.debug("No active users, skipping rate fetch")
        return

    pairs = database.get_all_active_pairs()
    logger.info(
        "Scheduled rate fetch: %d base currencies, %d active pairs",
        len(bases),
        len(pairs),
    )

    # Group targets by base
    targets_by_base: dict[str, list[str]] = {}
    for base, target in pairs:
        targets_by_base.setdefault(base, []).append(target)

    success = 0
    failed = 0
    for base, targets in targets_by_base.items():
        # get_rate for the first target triggers the fetch + cache for this base;
        # subsequent targets for the same base will hit the fresh cache.
        for target in targets:
            try:
                result = await get_rate(base, target)
                if result is not None:
                    success += 1
                else:
                    failed += 1
                    logger.warning("Failed to get rate for %s/%s", base, target)
            except Exception:
                failed += 1
                logger.exception("Error fetching rate for %s/%s", base, target)

    logger.info(
        "Scheduled rate fetch complete: %d success, %d failed", success, failed
    )
