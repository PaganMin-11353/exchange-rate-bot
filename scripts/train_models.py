#!/usr/bin/env python3
"""Train initial LightGBM models on the development machine.

Usage:
    # Train models for all preset currency pair combinations
    python scripts/train_models.py

    # Train for specific pairs
    python scripts/train_models.py SGD CNY SGD MYR USD CNY

    # Train for a single pair
    python scripts/train_models.py SGD CNY

The trained models (*.txt + *_meta.json) are saved to models/ and should
be committed to git so they're available on the deployment server.

Prerequisites:
    - The bot must have run at least once to populate rate_history with
      backfilled data, OR you can run the backfill standalone:
          python -c "import asyncio; from bot.services.exchange_api import backfill_preset_currencies; asyncio.run(backfill_preset_currencies())"
    - pip install -r requirements.txt
"""

import logging
import os
import sys

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot import database
from bot.config import PRESET_CURRENCIES
from bot.services.predictor import train_model

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs("models", exist_ok=True)
    database.initialize()

    args = sys.argv[1:]

    if args:
        # Parse pairs from arguments: SGD CNY SGD MYR ...
        if len(args) % 2 != 0:
            print("Usage: python scripts/train_models.py [BASE TARGET ...]")
            sys.exit(1)
        pairs = [(args[i], args[i + 1]) for i in range(0, len(args), 2)]
    else:
        # Train all preset combinations that have history
        pairs = []
        for base in PRESET_CURRENCIES:
            for target in PRESET_CURRENCIES:
                if base != target and database.has_rate_history(base, target):
                    pairs.append((base, target))

    logger.info("Training %d models", len(pairs))
    success = 0
    failed = 0

    for base, target in pairs:
        logger.info("Training %s/%s...", base, target)
        try:
            result = train_model(base, target)
            if result is not None:
                logger.info(
                    "  OK — RMSE=%.6f, direction_accuracy=%.1f%%",
                    result["rmse"],
                    result["direction_accuracy"] * 100,
                )
                success += 1
            else:
                logger.warning("  SKIP — insufficient data")
                failed += 1
        except Exception:
            logger.exception("  FAIL — error training %s/%s", base, target)
            failed += 1

    logger.info("Done: %d trained, %d skipped/failed", success, failed)
    logger.info("Models saved to models/ — commit them to git for deployment")


if __name__ == "__main__":
    main()
