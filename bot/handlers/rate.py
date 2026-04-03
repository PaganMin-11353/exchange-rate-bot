"""Handler for /rate — show current exchange rates for the user's targets."""

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot import database
from bot.services.analyzer import get_suggestion
from bot.services.exchange_api import get_rate
from bot.services.predictor import predict_next_days
from bot.utils.formatting import compute_change_and_avg, format_rate_message

logger = logging.getLogger(__name__)


async def _prediction_summary(base: str, target: str) -> str | None:
    """Build a short prediction summary string like '3.45 → 3.46 → 3.47'."""
    preds = await asyncio.to_thread(predict_next_days, base, target, 3)
    if not preds:
        return None
    return " → ".join(f"{p['rate']:.4f}" for p in preds) + " (3天)"


async def build_rate_message(user_id: int) -> str | None:
    """Build the rate message for a user. Returns None if no data available."""
    db_user = database.get_user(user_id)
    if not db_user:
        return None

    home = db_user["home_currency"]
    show_prediction = bool(db_user["show_prediction"])
    show_suggestion = bool(db_user["show_suggestion"])
    targets = database.get_user_targets(user_id)

    if not targets:
        return None

    target_data: list[dict] = []
    for target_currency in targets:
        result = await get_rate(home, target_currency)
        if result is None:
            logger.warning("Could not fetch rate for %s/%s", home, target_currency)
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
            entry["prediction_summary"] = await _prediction_summary(home, target_currency)

        target_data.append(entry)

    if not target_data:
        return None

    return format_rate_message(home, target_data, show_prediction, show_suggestion)


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /rate command: fetch and display current rates."""
    user = update.effective_user
    db_user = database.get_user(user.id)

    if not db_user:
        await update.message.reply_text(
            "您还没有注册，请先使用 /start 进行初始化设置。"
        )
        return

    targets = database.get_user_targets(user.id)
    if not targets:
        await update.message.reply_text(
            "您还没有设置跟踪目标货币，请使用 /settings 添加。"
        )
        return

    message = await build_rate_message(user.id)
    if not message:
        await update.message.reply_text("暂时无法获取汇率数据，请稍后再试。")
        return

    await update.message.reply_text(message, parse_mode="HTML")
