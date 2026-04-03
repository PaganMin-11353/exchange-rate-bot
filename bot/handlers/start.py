from telegram import Update
from telegram.ext import ContextTypes


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — stub for Phase 3."""
    await update.message.reply_text("Bot is starting up. Full onboarding coming soon.")
