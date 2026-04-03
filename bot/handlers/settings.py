"""Handler for /settings — modify user preferences via ConversationHandler."""

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
from bot.config import (
    COMMON_CURRENCIES,
    DEFAULT_TARGETS,
    DEFAULT_TARGETS_FALLBACK,
    SUPPORTED_INTERVALS,
)
from bot.handlers._common import compute_new_targets, interval_label, trigger_backfill

logger = logging.getLogger(__name__)

# Conversation states
CHOOSE_ACTION = 0
CHOOSE_NEW_HOME = 1
ENTER_CUSTOM_HOME = 2
CHOOSE_TARGET_ACTION = 3
ENTER_NEW_TARGET = 4
CHOOSE_REMOVE_TARGET = 5
CHOOSE_INTERVAL = 6


def _main_menu_text(user_id: int) -> str:
    user = database.get_user(user_id)
    targets = database.get_user_targets(user_id)
    return (
        f"当前设置：\n"
        f"持有货币: {user['home_currency']}\n"
        f"目标货币: {', '.join(targets) if targets else '无'}\n"
        f"推送间隔: {interval_label(user['interval_hours'])}\n\n"
        f"请选择要修改的项目："
    )


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("修改持有货币", callback_data="settings_home"),
            InlineKeyboardButton("修改目标货币", callback_data="settings_targets"),
        ],
        [
            InlineKeyboardButton("修改推送间隔", callback_data="settings_interval"),
            InlineKeyboardButton("取消", callback_data="settings_cancel"),
        ],
    ])


# ── Entry point ───────────────────────────────────────────────────


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle /settings command."""
    user = update.effective_user
    existing = database.get_user(user.id)

    if not existing:
        await update.message.reply_text("请先使用 /start 初始化")
        return ConversationHandler.END

    text = _main_menu_text(user.id)
    await update.message.reply_text(text, reply_markup=_main_menu_keyboard())
    return CHOOSE_ACTION


# ── Main action router ────────────────────────────────────────────


async def choose_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "settings_cancel":
        await query.edit_message_text("设置已取消")
        return ConversationHandler.END

    if data == "settings_home":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("SGD", callback_data="sethome_SGD"),
                InlineKeyboardButton("MYR", callback_data="sethome_MYR"),
                InlineKeyboardButton("CNY", callback_data="sethome_CNY"),
                InlineKeyboardButton("USD", callback_data="sethome_USD"),
            ],
            [
                InlineKeyboardButton("其他", callback_data="sethome_OTHER"),
                InlineKeyboardButton("返回", callback_data="settings_back"),
            ],
        ])
        await query.edit_message_text("请选择新的持有货币：", reply_markup=keyboard)
        return CHOOSE_NEW_HOME

    if data == "settings_targets":
        return await _show_target_menu(query, update.effective_user.id)

    if data == "settings_interval":
        buttons = []
        for label in SUPPORTED_INTERVALS:
            buttons.append(InlineKeyboardButton(label, callback_data=f"interval_{label}"))
        keyboard = InlineKeyboardMarkup(
            [buttons[:2], buttons[2:] + [InlineKeyboardButton("返回", callback_data="settings_back")]]
        )
        await query.edit_message_text("请选择推送间隔：", reply_markup=keyboard)
        return CHOOSE_INTERVAL

    return CHOOSE_ACTION


# ── Home currency ─────────────────────────────────────────────────


async def choose_new_home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "settings_back":
        text = _main_menu_text(update.effective_user.id)
        await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
        return CHOOSE_ACTION

    if data == "sethome_OTHER":
        await query.edit_message_text("请输入您的货币代码（如 EUR、GBP、THB）：")
        return ENTER_CUSTOM_HOME

    if data.startswith("sethome_"):
        currency = data.removeprefix("sethome_")
        return await _apply_new_home(query, update.effective_user.id, currency)

    return CHOOSE_NEW_HOME


async def enter_custom_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if text not in COMMON_CURRENCIES:
        await update.message.reply_text("无效的货币代码，请重新输入或使用 /cancel 取消")
        return ENTER_CUSTOM_HOME

    user_id = update.effective_user.id
    # We can't edit a previous callback message from a text handler,
    # so we reply with a new message and return to the main menu.
    return await _apply_new_home_text(update, user_id, text)


def _change_home_currency(user_id: int, currency: str) -> tuple[list[str], str]:
    """Change home currency, compute new targets, trigger backfill. Returns (new_targets, response_text)."""
    old_user = database.get_user(user_id)
    old_targets = database.get_user_targets(user_id)

    database.update_user_home_currency(user_id, currency)
    new_targets = compute_new_targets(
        currency, old_user["home_currency"], old_targets, DEFAULT_TARGETS, DEFAULT_TARGETS_FALLBACK
    )
    database.set_user_targets(user_id, new_targets)
    trigger_backfill(currency, new_targets)

    text = (
        f"持有货币已更新为 {currency}\n"
        f"目标货币已调整为: {', '.join(new_targets)}\n\n"
    )
    text += _main_menu_text(user_id)
    return new_targets, text


async def _apply_new_home(query, user_id: int, currency: str) -> int:
    """Change home currency (callback query path)."""
    _, text = _change_home_currency(user_id, currency)
    await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
    return CHOOSE_ACTION


async def _apply_new_home_text(update: Update, user_id: int, currency: str) -> int:
    """Change home currency (text input path)."""
    _, text = _change_home_currency(user_id, currency)
    await update.message.reply_text(text, reply_markup=_main_menu_keyboard())
    return CHOOSE_ACTION


# ── Target currencies ─────────────────────────────────────────────


async def _show_target_menu(query, user_id: int) -> int:
    targets = database.get_user_targets(user_id)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("添加目标", callback_data="target_add"),
            InlineKeyboardButton("删除目标", callback_data="target_remove"),
        ],
        [InlineKeyboardButton("返回", callback_data="settings_back_from_targets")],
    ])
    await query.edit_message_text(
        f"当前目标货币: {', '.join(targets) if targets else '无'}",
        reply_markup=keyboard,
    )
    return CHOOSE_TARGET_ACTION


async def choose_target_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "settings_back_from_targets":
        text = _main_menu_text(user_id)
        await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
        return CHOOSE_ACTION

    if data == "target_add":
        targets = database.get_user_targets(user_id)
        if len(targets) >= 3:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="target_back_to_menu")],
            ])
            await query.edit_message_text(
                "已达到最大数量（3个），请先删除一个",
                reply_markup=keyboard,
            )
            return CHOOSE_TARGET_ACTION
        await query.edit_message_text("请输入要添加的货币代码（如 EUR、GBP）：")
        return ENTER_NEW_TARGET

    if data == "target_remove":
        targets = database.get_user_targets(user_id)
        if not targets:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("返回", callback_data="target_back_to_menu")],
            ])
            await query.edit_message_text("当前没有目标货币", reply_markup=keyboard)
            return CHOOSE_TARGET_ACTION
        buttons = [
            InlineKeyboardButton(t, callback_data=f"rmtarget_{t}") for t in targets
        ]
        keyboard = InlineKeyboardMarkup(
            [buttons, [InlineKeyboardButton("返回", callback_data="target_back_to_menu")]]
        )
        await query.edit_message_text("请选择要删除的目标货币：", reply_markup=keyboard)
        return CHOOSE_REMOVE_TARGET

    if data == "target_back_to_menu":
        return await _show_target_menu(query, user_id)

    return CHOOSE_TARGET_ACTION


async def enter_new_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    user_id = update.effective_user.id
    user = database.get_user(user_id)

    if text not in COMMON_CURRENCIES:
        await update.message.reply_text("无效的货币代码，请重新输入或使用 /cancel 取消")
        return ENTER_NEW_TARGET

    if text == user["home_currency"]:
        await update.message.reply_text("不能将持有货币添加为目标货币，请输入其他货币代码：")
        return ENTER_NEW_TARGET

    existing_targets = database.get_user_targets(user_id)
    if text in existing_targets:
        await update.message.reply_text(f"{text} 已在目标列表中，请输入其他货币代码：")
        return ENTER_NEW_TARGET

    success = database.add_user_target(user_id, text)
    if not success:
        await update.message.reply_text("已达到最大数量（3个），请先删除一个")
        # Go back to target action menu
        targets = database.get_user_targets(user_id)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("添加目标", callback_data="target_add"),
                InlineKeyboardButton("删除目标", callback_data="target_remove"),
            ],
            [InlineKeyboardButton("返回", callback_data="settings_back_from_targets")],
        ])
        await update.message.reply_text(
            f"当前目标货币: {', '.join(targets)}",
            reply_markup=keyboard,
        )
        return CHOOSE_TARGET_ACTION

    # Trigger backfill for new pair
    trigger_backfill(user["home_currency"], [text])

    targets = database.get_user_targets(user_id)
    text_msg = f"已添加 {text}\n当前目标货币: {', '.join(targets)}\n\n"
    text_msg += _main_menu_text(user_id)
    await update.message.reply_text(text_msg, reply_markup=_main_menu_keyboard())
    return CHOOSE_ACTION


async def choose_remove_target_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "target_back_to_menu":
        return await _show_target_menu(query, user_id)

    if data.startswith("rmtarget_"):
        currency = data.removeprefix("rmtarget_")
        database.remove_user_target(user_id, currency)
        targets = database.get_user_targets(user_id)
        text = f"已删除 {currency}\n当前目标货币: {', '.join(targets) if targets else '无'}\n\n"
        text += _main_menu_text(user_id)
        await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
        return CHOOSE_ACTION

    return CHOOSE_REMOVE_TARGET


# ── Interval ──────────────────────────────────────────────────────


async def choose_interval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "settings_back":
        text = _main_menu_text(user_id)
        await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
        return CHOOSE_ACTION

    if data.startswith("interval_"):
        label = data.removeprefix("interval_")
        hours = SUPPORTED_INTERVALS.get(label)
        if hours is None:
            return CHOOSE_INTERVAL

        database.update_user_interval(user_id, hours)
        text = f"推送间隔已更新为: {label}\n\n"
        text += _main_menu_text(user_id)
        await query.edit_message_text(text, reply_markup=_main_menu_keyboard())
        return CHOOSE_ACTION

    return CHOOSE_INTERVAL


# ── Cancel ────────────────────────────────────────────────────────


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("设置已取消")
    return ConversationHandler.END


# ── ConversationHandler ───────────────────────────────────────────


settings_conversation = ConversationHandler(
    entry_points=[CommandHandler("settings", settings_command)],
    states={
        CHOOSE_ACTION: [
            CallbackQueryHandler(choose_action_callback),
        ],
        CHOOSE_NEW_HOME: [
            CallbackQueryHandler(choose_new_home_callback),
        ],
        ENTER_CUSTOM_HOME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_custom_home),
        ],
        CHOOSE_TARGET_ACTION: [
            CallbackQueryHandler(choose_target_action_callback),
        ],
        ENTER_NEW_TARGET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, enter_new_target),
        ],
        CHOOSE_REMOVE_TARGET: [
            CallbackQueryHandler(choose_remove_target_callback),
        ],
        CHOOSE_INTERVAL: [
            CallbackQueryHandler(choose_interval_callback),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_user=True,
    per_chat=True,
)
