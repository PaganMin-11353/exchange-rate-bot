import logging
import os

from telegram.ext import Application, CommandHandler

from bot.config import TELEGRAM_TOKEN, LOG_LEVEL
from bot import database
from bot.handlers.start import start_handler


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, LOG_LEVEL),
    )
    logger = logging.getLogger(__name__)

    # Ensure data and models directories exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    # Initialize database
    database.initialize()
    logger.info("Database initialized")

    # Build application
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))

    # Start polling
    logger.info("Bot starting in polling mode")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
