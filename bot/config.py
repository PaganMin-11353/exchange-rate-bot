import os
from zoneinfo import ZoneInfo

# Telegram
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise SystemExit("ERROR: TELEGRAM_BOT_TOKEN environment variable is required")

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

# All supported currency codes (from ExchangeRate-API, snapshot 2026-04)
SUPPORTED_CURRENCIES = frozenset([
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN",
    "BAM", "BBD", "BDT", "BGN", "BHD", "BIF", "BMD", "BND", "BOB", "BRL",
    "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHF", "CLP", "CNY",
    "COP", "CRC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD", "EGP",
    "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD",
    "GNF", "GTQ", "GYD", "HKD", "HNL", "HTG", "HUF", "IDR", "ILS", "INR",
    "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR", "KMF",
    "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD",
    "MAD", "MDL", "MGA", "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR",
    "MWK", "MXN", "MYR", "MZN", "NAD", "NGN", "NIO", "NOK", "NPR", "NZD",
    "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON",
    "RSD", "RUB", "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP",
    "SLE", "SOS", "SRD", "SSP", "STN", "SYP", "SZL", "THB", "TJS", "TMT",
    "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "UYU",
    "UZS", "VES", "VND", "VUV", "WST", "XAF", "XCD", "XDR", "XOF", "XPF",
    "YER", "ZAR", "ZMW",
])
