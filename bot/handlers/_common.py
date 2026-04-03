"""Shared utilities for bot handlers."""

import asyncio
import logging

from bot import database
from bot.config import SUPPORTED_INTERVALS
from bot.services.exchange_api import backfill_history

logger = logging.getLogger(__name__)


def interval_label(hours: int) -> str:
    """Map interval_hours to a Chinese display label."""
    for label, h in SUPPORTED_INTERVALS.items():
        if h == hours:
            return label
    return f"每{hours}小时"


def trigger_backfill(home: str, targets: list[str]) -> None:
    """Fire-and-forget backfill for pairs that lack history."""
    for target in targets:
        if not database.has_rate_history(home, target):
            task = asyncio.create_task(backfill_history(home, target))
            task.add_done_callback(_log_backfill_error)


def _log_backfill_error(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background backfill failed: %s", exc)


def compute_new_targets(
    new_home: str,
    old_home: str,
    old_targets: list[str],
    default_targets: dict[str, list[str]],
    fallback: list[str],
) -> list[str]:
    """Compute new target list when home currency changes."""
    if new_home in default_targets:
        new_targets = list(default_targets[new_home])
    else:
        new_targets = [c for c in fallback if c != new_home]

    # If old targets contained the new home, try to swap with old home
    if new_home in old_targets:
        adjusted = [t for t in old_targets if t != new_home]
        if old_home not in adjusted and len(adjusted) < 3:
            adjusted.append(old_home)
        new_targets = adjusted if adjusted else new_targets

    return new_targets
