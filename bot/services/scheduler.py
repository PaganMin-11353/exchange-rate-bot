"""Scheduled jobs for fetching and storing exchange rates."""

import asyncio
import logging
from datetime import datetime, timedelta

from telegram.error import Forbidden

from bot import database
from bot.config import TZ
from bot.services.analyzer import get_suggestion
from bot.services.exchange_api import get_rate
from bot.services.predictor import predict_next_days, retrain_all_models
from bot.utils.formatting import compute_change_and_avg, format_rate_message

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


async def dispatch_notifications(context) -> None:
    """Job callback: send rate notifications to users whose interval has elapsed.

    Called by JobQueue every NOTIFICATION_CHECK_INTERVAL_SECONDS.
    """
    users = database.get_active_users()
    if not users:
        logger.debug("No active users, skipping notification dispatch")
        return

    now = datetime.now(TZ)
    sent = 0
    skipped = 0
    errors = 0

    for user in users:
        user_id = user["user_id"]
        chat_id = user["chat_id"]
        interval_hours = user["interval_hours"]
        last_notified_at = user["last_notified_at"]

        # Check if enough time has elapsed since last notification
        if last_notified_at:
            try:
                last_dt = datetime.fromisoformat(last_notified_at)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=TZ)
            except (ValueError, TypeError):
                # If the stored timestamp is malformed, treat as never notified
                last_dt = None
        else:
            last_dt = None

        if last_dt is not None:
            next_due = last_dt + timedelta(hours=interval_hours)
            if now < next_due:
                skipped += 1
                continue

        # Build the notification message (same as /rate)
        home = user["home_currency"]
        show_prediction = bool(user["show_prediction"])
        show_suggestion = bool(user["show_suggestion"])
        targets = database.get_user_targets(user_id)
        if not targets:
            skipped += 1
            continue

        target_data: list[dict] = []
        for target_currency in targets:
            result = await get_rate(home, target_currency)
            if result is None:
                continue

            rate, _fetched_at = result
            change_24h, avg_7d = compute_change_and_avg(home, target_currency)

            entry: dict = {
                "target_currency": target_currency,
                "rate": rate,
                "change_24h": change_24h,
                "avg_7d": avg_7d,
            }

            if show_suggestion:
                history = database.get_rate_history(home, target_currency, limit=30)
                entry["suggestion"] = get_suggestion(rate, history)

            if show_prediction:
                preds = await asyncio.to_thread(predict_next_days, home, target_currency, 3)
                if preds:
                    entry["prediction_summary"] = " → ".join(
                        f"{p['rate']:.4f}" for p in preds
                    ) + " (3天)"

            target_data.append(entry)

        if not target_data:
            skipped += 1
            continue

        message = format_rate_message(home, target_data, show_prediction, show_suggestion)

        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
            database.update_last_notified(user_id, now.isoformat(timespec="seconds"))
            sent += 1
        except Forbidden:
            logger.warning(
                "User %d has blocked the bot, deactivating", user_id
            )
            database.deactivate_user(user_id)
            errors += 1
        except Exception:
            logger.exception(
                "Failed to send notification to user %d (chat %d)", user_id, chat_id
            )
            errors += 1

    logger.info(
        "Notification dispatch complete: %d sent, %d skipped, %d errors",
        sent,
        skipped,
        errors,
    )


async def retrain_models(context) -> None:
    """Job callback: retrain all LightGBM models weekly."""
    logger.info("Starting weekly model retrain")
    try:
        await retrain_all_models()
    except Exception:
        logger.exception("Weekly model retrain failed")
