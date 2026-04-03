import asyncio
import logging
import logging.handlers
import os
from datetime import datetime, timedelta

from telegram.ext import Application, CommandHandler

from bot.config import TELEGRAM_TOKEN, LOG_LEVEL, RATE_FETCH_INTERVAL_SECONDS, NOTIFICATION_CHECK_INTERVAL_SECONDS, TZ
from bot import database
from bot.handlers.start import start_conversation
from bot.handlers.settings import settings_conversation
from bot.handlers.rate import rate_command
from bot.handlers.predict import predict_command
from bot.handlers.reset import reset_command
from bot.services.exchange_api import backfill_preset_currencies
from bot.services.scheduler import fetch_and_store_rates, dispatch_notifications, retrain_models


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
    # Ensure data and models directories exist (before setting up file logging)
    os.makedirs("data", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    # Configure logging: console at INFO, file at DEBUG with rotation
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler — INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))
    console_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(console_handler)

    # File handler — DEBUG level, 5 MB rotation, 2 backups
    file_handler = logging.handlers.RotatingFileHandler(
        "data/bot.log", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    root_logger.addHandler(file_handler)

    logger = logging.getLogger(__name__)

    # Initialize database
    database.initialize()
    logger.info("Database initialized")

    # Build application
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Error handler
    async def error_handler(update, context):
        logger.exception("Unhandled exception: %s", context.error)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text("出现错误，请稍后重试。")
            except Exception:
                pass

    app.add_error_handler(error_handler)

    # Register conversation handlers
    app.add_handler(start_conversation)
    app.add_handler(settings_conversation)

    # Register simple command handlers
    app.add_handler(CommandHandler("rate", rate_command))
    app.add_handler(CommandHandler("predict", predict_command))
    app.add_handler(CommandHandler("reset", reset_command))

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

    app.job_queue.run_repeating(
        dispatch_notifications,
        interval=NOTIFICATION_CHECK_INTERVAL_SECONDS,
        first=30,  # first run 30 seconds after startup
        name="dispatch_notifications",
    )
    logger.info(
        "Notification dispatch job registered (every %d seconds)",
        NOTIFICATION_CHECK_INTERVAL_SECONDS,
    )

    # Weekly model retrain: every Monday at 03:00 UTC+8
    # Calculate seconds until next Monday 03:00 UTC+8
    now = datetime.now(TZ)
    # days_until_monday: 0=Mon, 1=Tue, ... 6=Sun
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0:
        # Today is Monday; if already past 03:00, schedule for next Monday
        target_time = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= target_time:
            days_until_monday = 7
    next_monday_3am = now.replace(
        hour=3, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_until_monday)
    first_retrain = (next_monday_3am - now).total_seconds()

    app.job_queue.run_repeating(
        retrain_models,
        interval=7 * 24 * 3600,
        first=first_retrain,
        name="retrain_models",
    )
    logger.info(
        "Model retrain job registered (weekly Monday 03:00 UTC+8, first in %.0f seconds)",
        first_retrain,
    )

    # Start polling
    logger.info("Bot starting in polling mode")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
