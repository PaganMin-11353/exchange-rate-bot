"""Handler for /rate — show current exchange rates for the user's targets."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot import database
from bot.services.analyzer import get_suggestion
from bot.services.exchange_api import get_rate
from bot.utils.formatting import compute_change_and_avg, format_rate_message

logger = logging.getLogger(__name__)


async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /rate command: fetch and display current rates."""
    user = update.effective_user
    db_user = database.get_user(user.id)

    if not db_user:
        await update.message.reply_text(
            "您还没有注册，请先使用 /start 进行初始化设置。"
        )
        return

    home = db_user["home_currency"]
    targets = database.get_user_targets(user.id)

    if not targets:
        await update.message.reply_text(
            "您还没有设置跟踪目标货币，请使用 /settings 添加。"
        )
        return

    # Build target data for each currency pair
    target_data: list[dict] = []
    for target_currency in targets:
        result = await get_rate(home, target_currency)
        if result is None:
            logger.warning("Could not fetch rate for %s/%s", home, target_currency)
            continue

        rate, _fetched_at = result
        change_24h, avg_7d = compute_change_and_avg(home, target_currency)

        history = database.get_rate_history(home, target_currency, days=30)
        suggestion = get_suggestion(rate, history)

        target_data.append({
            "target_currency": target_currency,
            "rate": rate,
            "change_24h": change_24h,
            "avg_7d": avg_7d,
            "suggestion": suggestion,
        })

    if not target_data:
        await update.message.reply_text(
            "暂时无法获取汇率数据，请稍后再试。"
        )
        return

    message = format_rate_message(home, target_data)
    await update.message.reply_text(message)
