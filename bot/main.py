import asyncio
import logging
import os

from telegram.ext import Application, CommandHandler

from bot.config import TELEGRAM_TOKEN, LOG_LEVEL, RATE_FETCH_INTERVAL_SECONDS
from bot import database
from bot.handlers.start import start_conversation
from bot.handlers.settings import settings_conversation
from bot.services.exchange_api import backfill_preset_currencies
from bot.services.scheduler import fetch_and_store_rates


_background_tasks: set[asyncio.Task] = set()


async def post_init(application) -> None:
    """Run after the Application has been initialized.

    Kicks off the historical backfill in the background so it doesn't
    block the bot from responding to commands.
    """
    logger = logging.getLogger(__name__)
    logger.info("Running post-init: scheduling background backfill")
    task = asyncio.create_task(_run_backfill())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _run_backfill() -> None:
    """Wrapper so backfill exceptions are logged, not silently swallowed."""
    logger = logging.getLogger(__name__)
    try:
        await backfill_preset_currencies()
    except Exception:
        logger.exception("Background backfill failed")


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
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Register conversation handlers
    app.add_handler(start_conversation)
    app.add_handler(settings_conversation)

    # Register scheduled jobs
    app.job_queue.run_repeating(
        fetch_and_store_rates,
        interval=RATE_FETCH_INTERVAL_SECONDS,
        first=10,  # first run 10 seconds after startup
        name="fetch_and_store_rates",
    )
    logger.info(
        "Rate fetch job registered (every %d seconds)", RATE_FETCH_INTERVAL_SECONDS
    )

    # Start polling
    logger.info("Bot starting in polling mode")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
