"""Handler for /start — user onboarding via ConversationHandler."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot import database
from bot.config import SUPPORTED_CURRENCIES, DEFAULT_TARGETS, DEFAULT_TARGETS_FALLBACK
from bot.handlers._common import interval_label, trigger_backfill
from bot.handlers.rate import build_rate_message

logger = logging.getLogger(__name__)

# Conversation states
CHOOSE_HOME = 0
ENTER_CUSTOM_HOME = 1


def _settings_summary(home: str, targets: list[str], interval_hours: int) -> str:
    return (
        f"设置完成！\n"
        f"持有货币: {home}\n"
        f"跟踪目标: {', '.join(targets)}\n"
        f"推送间隔: {interval_label(interval_hours)}\n\n"
        f"使用 /settings 修改设置\n"
        f"使用 /rate 查看当前汇率"
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /start."""
    user = update.effective_user
    existing = database.get_user(user.id)

    if existing:
        targets = database.get_user_targets(user.id)
        home = existing["home_currency"]
        interval = existing["interval_hours"]
        text = (
            f"您已完成初始化。\n"
            f"持有货币: {home}\n"
            f"跟踪目标: {', '.join(targets) if targets else '无'}\n"
            f"推送间隔: {interval_label(interval)}\n\n"
            f"是否重新设置？"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("重新设置", callback_data="start_reconfigure"),
                InlineKeyboardButton("保持不变", callback_data="start_keep"),
            ]
        ])
        await update.message.reply_text(text, reply_markup=keyboard)
        return CHOOSE_HOME

    # New user — show currency picker
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("SGD", callback_data="home_SGD"),
            InlineKeyboardButton("MYR", callback_data="home_MYR"),
            InlineKeyboardButton("CNY", callback_data="home_CNY"),
            InlineKeyboardButton("USD", callback_data="home_USD"),
        ],
        [InlineKeyboardButton("其他", callback_data="home_OTHER")],
    ])
    await update.message.reply_text(
        "欢迎使用汇率提醒机器人！请选择您的持有货币（您日常使用的货币）：",
        reply_markup=keyboard,
    )
    return CHOOSE_HOME


async def choose_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle inline button press for home currency selection."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "start_keep":
        await query.edit_message_text("好的，保持当前设置不变。使用 /settings 可随时修改。")
        return ConversationHandler.END

    if data == "start_reconfigure":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("SGD", callback_data="home_SGD"),
                InlineKeyboardButton("MYR", callback_data="home_MYR"),
                InlineKeyboardButton("CNY", callback_data="home_CNY"),
                InlineKeyboardButton("USD", callback_data="home_USD"),
            ],
            [InlineKeyboardButton("其他", callback_data="home_OTHER")],
        ])
        await query.edit_message_text(
            "请选择您的持有货币（您日常使用的货币）：",
            reply_markup=keyboard,
        )
        return CHOOSE_HOME

    if data == "home_OTHER":
        await query.edit_message_text("请输入您的货币代码（如 EUR、GBP、THB）：")
        return ENTER_CUSTOM_HOME

    # Preset currency selected
    if data.startswith("home_"):
        currency = data.removeprefix("home_")
        return await _save_user(update, context, currency)

    return CHOOSE_HOME


async def enter_custom_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle free-text input for a custom home currency."""
    text = update.message.text.strip().upper()

    if text not in SUPPORTED_CURRENCIES:
        await update.message.reply_text("无效的货币代码，请重新输入或使用 /cancel 取消")
        return ENTER_CUSTOM_HOME

    return await _save_user(update, context, text)


async def _save_user(update: Update, context: ContextTypes.DEFAULT_TYPE, home_currency: str) -> int:
    """Persist the user and their default targets, then confirm."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Determine targets
    if home_currency in DEFAULT_TARGETS:
        targets = DEFAULT_TARGETS[home_currency]
    else:
        targets = [c for c in DEFAULT_TARGETS_FALLBACK if c != home_currency]

    database.upsert_user(user.id, chat_id, user.username, home_currency)
    database.set_user_targets(user.id, targets)

    # Trigger background backfill for new pairs
    trigger_backfill(home_currency, targets)

    summary = _settings_summary(home_currency, targets, 24)

    # Reply via callback edit or direct message depending on how we got here
    if update.callback_query:
        await update.callback_query.edit_message_text(summary)
    else:
        await update.message.reply_text(summary)

    # Send first rate notification immediately
    message = await build_rate_message(user.id)
    if message:
        await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("设置已取消。")
    return ConversationHandler.END


start_conversation = ConversationHandler(
    entry_points=[CommandHandler("start", start_command)],
    states={
        CHOOSE_HOME: [
            CallbackQueryHandler(choose_home_callback),
        ],
        ENTER_CUSTOM_HOME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_home),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_user=True,
    per_chat=True,
    conversation_timeout=300,
)
