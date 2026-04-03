"""Handler for /reset — delete user data and restart onboarding."""

from telegram import Update
from telegram.ext import ContextTypes

from bot import database


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reset — wipe user data so they can re-run /start fresh."""
    user = update.effective_user
    existing = database.get_user(user.id)

    if not existing:
        await update.message.reply_text("您还没有注册，请使用 /start 开始。")
        return

    database.delete_user(user.id)
    await update.message.reply_text("已重置所有设置。请使用 /start 重新开始。")
