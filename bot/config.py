import os
from zoneinfo import ZoneInfo

# Telegram
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Exchange Rate API
API_KEY = os.environ.get("EXCHANGERATE_API_KEY", "")
USE_OPEN_API = os.environ.get("USE_OPEN_API", "false").lower() == "true"

# Database
DB_PATH = os.environ.get("DB_PATH", "data/bot.db")

# Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Timezone
TZ = ZoneInfo("Asia/Shanghai")

# Cache
CACHE_TTL_HOURS = 23
RATE_FETCH_INTERVAL_SECONDS = 3600  # 1 hour
NOTIFICATION_CHECK_INTERVAL_SECONDS = 900  # 15 min
MONTHLY_API_CALL_LIMIT = 1400  # safety margin under 1500

# Suggestion
SUGGESTION_THRESHOLD_PCT = 1.5

# Notification intervals (display name → hours)
SUPPORTED_INTERVALS = {
    "每天": 24,
    "每2天": 48,
    "每周": 168,
    "每2周": 336,
}

# Default currencies to backfill on startup
PRESET_CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CHF", "CAD", "CNY", "SGD", "MYR"]

# Smart defaults: home_currency → [target1, target2, target3]
DEFAULT_TARGETS = {
    "SGD": ["MYR", "CNY", "USD"],
    "MYR": ["SGD", "CNY", "USD"],
    "CNY": ["SGD", "MYR", "USD"],
    "USD": ["SGD", "MYR", "CNY"],
}
DEFAULT_TARGETS_FALLBACK = ["SGD", "CNY", "USD"]

# Common currencies for UI display
COMMON_CURRENCIES = [
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD",
    "CNY", "HKD", "SGD", "MYR", "KRW", "INR", "THB", "IDR",
    "PHP", "TWD", "BRL", "MXN", "ZAR", "TRY", "AED", "SAR",
]
