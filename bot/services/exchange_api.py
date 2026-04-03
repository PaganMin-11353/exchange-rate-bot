"""Exchange rate API clients and cache-aware rate getter."""

import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from bot import database
from bot.config import (
    API_KEY,
    CACHE_TTL_HOURS,
    MONTHLY_API_CALL_LIMIT,
    PRESET_CURRENCIES,
    TZ,
    USE_OPEN_API,
)

logger = logging.getLogger(__name__)

_FRANKFURTER_BASE = "https://api.frankfurter.dev/v1"
_CHUNK_DAYS = 365  # split Frankfurter requests into ~1-year chunks


# ── Frankfurter (historical backfill) ──────────────────────────────


async def backfill_history(base: str, target: str, years: int = 5) -> int:
    """Fetch historical rates from Frankfurter and store them.

    Returns the total number of rows inserted.
    """
    today = datetime.now(TZ).date()
    start = today - timedelta(days=years * 365)
    total_inserted = 0

    async with httpx.AsyncClient(timeout=30) as client:
        chunk_start = start
        while chunk_start < today:
            chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS), today)
            url = (
                f"{_FRANKFURTER_BASE}/{chunk_start.isoformat()}"
                f"..{chunk_end.isoformat()}?from={base}&to={target}"
            )
            logger.debug("Frankfurter request: %s", url)

            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    logger.warning(
                        "Frankfurter: currency pair %s/%s not supported (ECB), skipping",
                        base,
                        target,
                    )
                    return total_inserted
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Frankfurter HTTP error for %s/%s (%s-%s): %s",
                    base,
                    target,
                    chunk_start,
                    chunk_end,
                    exc,
                )
                chunk_start = chunk_end + timedelta(days=1)
                continue
            except httpx.RequestError as exc:
                logger.warning(
                    "Frankfurter network error for %s/%s: %s",
                    base,
                    target,
                    exc,
                )
                chunk_start = chunk_end + timedelta(days=1)
                continue

            data = resp.json()
            rates_by_date = data.get("rates", {})
            rows: list[tuple[str, str, float, str]] = []
            for date_str, targets_map in rates_by_date.items():
                rate = targets_map.get(target)
                if rate is not None:
                    rows.append((base, target, float(rate), date_str))

            if rows:
                database.insert_rates_bulk(rows)
                total_inserted += len(rows)
                logger.debug(
                    "Inserted %d rows for %s/%s (%s - %s)",
                    len(rows),
                    base,
                    target,
                    chunk_start,
                    chunk_end,
                )

            chunk_start = chunk_end + timedelta(days=1)

    logger.info(
        "Backfill complete for %s/%s: %d rows inserted", base, target, total_inserted
    )
    return total_inserted


async def _backfill_multi_target(
    base: str, targets: list[str], years: int = 5
) -> int:
    """Backfill multiple targets in a single Frankfurter call per chunk.

    Frankfurter supports `?from=USD&to=CNY,SGD,MYR`.
    """
    today = datetime.now(TZ).date()
    start = today - timedelta(days=years * 365)
    total_inserted = 0
    targets_param = ",".join(targets)

    async with httpx.AsyncClient(timeout=30) as client:
        chunk_start = start
        while chunk_start < today:
            chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS), today)
            url = (
                f"{_FRANKFURTER_BASE}/{chunk_start.isoformat()}"
                f"..{chunk_end.isoformat()}?from={base}&to={targets_param}"
            )
            logger.debug("Frankfurter multi-target request: %s", url)

            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    logger.warning(
                        "Frankfurter: base %s or targets %s not supported, skipping",
                        base,
                        targets_param,
                    )
                    return total_inserted
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "Frankfurter HTTP error for %s->%s (%s-%s): %s",
                    base,
                    targets_param,
                    chunk_start,
                    chunk_end,
                    exc,
                )
                chunk_start = chunk_end + timedelta(days=1)
                continue
            except httpx.RequestError as exc:
                logger.warning(
                    "Frankfurter network error for %s->%s: %s",
                    base,
                    targets_param,
                    exc,
                )
                chunk_start = chunk_end + timedelta(days=1)
                continue

            data = resp.json()
            rates_by_date = data.get("rates", {})
            rows: list[tuple[str, str, float, str]] = []
            for date_str, targets_map in rates_by_date.items():
                for tgt, rate in targets_map.items():
                    rows.append((base, tgt, float(rate), date_str))

            if rows:
                database.insert_rates_bulk(rows)
                total_inserted += len(rows)
                logger.debug(
                    "Inserted %d rows for %s->%s (%s - %s)",
                    len(rows),
                    base,
                    targets_param,
                    chunk_start,
                    chunk_end,
                )

            chunk_start = chunk_end + timedelta(days=1)

    logger.info(
        "Multi-target backfill complete for %s->%s: %d rows",
        base,
        targets_param,
        total_inserted,
    )
    return total_inserted


# ── ExchangeRate-API (daily latest rates) ──────────────────────────


async def fetch_latest_rates(base: str) -> dict[str, float] | None:
    """Fetch latest rates from ExchangeRate-API.

    Returns dict of target->rate, or None on failure.
    Respects MONTHLY_API_CALL_LIMIT — returns None if limit reached.
    """
    # Check monthly API usage before making a call
    current_calls = database.get_monthly_api_calls()
    if current_calls >= MONTHLY_API_CALL_LIMIT:
        logger.warning(
            "Monthly API call limit reached (%d/%d), skipping fetch for %s — serving stale cache",
            current_calls,
            MONTHLY_API_CALL_LIMIT,
            base,
        )
        return None

    if USE_OPEN_API:
        url = f"https://open.er-api.com/v6/latest/{base}"
    else:
        if not API_KEY:
            logger.error("EXCHANGERATE_API_KEY not set and USE_OPEN_API is false")
            return None
        url = f"https://v6.exchangerate-api.com/v6/{API_KEY}/latest/{base}"

    logger.debug("ExchangeRate-API request for base: %s", base)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("ExchangeRate-API error for %s: %s", base, exc)
        return None

    data = resp.json()

    # Open API uses "rates", keyed API uses "conversion_rates"
    rates = data.get("conversion_rates") or data.get("rates")
    if not rates or not isinstance(rates, dict):
        logger.warning("ExchangeRate-API unexpected response for %s: %s", base, data)
        return None

    # Track successful API call
    new_count = database.increment_api_calls()
    logger.debug("API call count this month: %d/%d", new_count, MONTHLY_API_CALL_LIMIT)

    # Filter out base currency itself and ensure float values
    return {k: float(v) for k, v in rates.items() if k != base}


# ── Cache-aware rate getter ────────────────────────────────────────


async def get_rate(base: str, target: str) -> tuple[float, str] | None:
    """Get a rate, using cache if fresh, otherwise fetching live.

    Returns (rate, fetched_at_iso) or None.
    """
    cached = database.get_cached_rates(base)
    if cached:
        fetched_at = cached["fetched_at"]
        age = datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at).replace(tzinfo=timezone.utc)
        if age < timedelta(hours=CACHE_TTL_HOURS):
            rates = json.loads(cached["rates_json"])
            rate = rates.get(target)
            if rate is not None:
                return (float(rate), fetched_at)

    # Cache miss or stale — fetch fresh
    rates = await fetch_latest_rates(base)
    if rates is None:
        # Fall back to stale cache if available
        if cached:
            stale_rates = json.loads(cached["rates_json"])
            rate = stale_rates.get(target)
            if rate is not None:
                logger.info("Using stale cache for %s/%s", base, target)
                return (float(rate), cached["fetched_at"])
        return None

    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    database.update_cache(base, json.dumps(rates), now_iso)

    # Append to rate_history — only tracked pairs, not all ~160 currencies
    today_str = datetime.now(TZ).date().isoformat()
    active_targets = {t for _, t in database.get_all_active_pairs() if _ == base}
    active_targets.update(t for t in PRESET_CURRENCIES if t != base)
    for tgt in active_targets:
        rate_val = rates.get(tgt)
        if rate_val is not None:
            database.insert_rate(base, tgt, float(rate_val), today_str)

    rate = rates.get(target)
    if rate is None:
        return None
    return (float(rate), now_iso)


# ── Startup backfill ───────────────────────────────────────────────


async def backfill_preset_currencies() -> None:
    """Backfill historical rates for all PRESET_CURRENCIES combinations.

    Uses Frankfurter multi-target queries to batch efficiently.
    Skips pairs that already have history data.
    """
    logger.info("Starting preset currency backfill...")
    total = 0

    for base in PRESET_CURRENCIES:
        # Determine which targets still need backfill
        targets_needed: list[str] = []
        for target in PRESET_CURRENCIES:
            if target == base:
                continue
            if not database.has_rate_history(base, target):
                targets_needed.append(target)

        if not targets_needed:
            logger.debug("Backfill: %s already has history for all targets", base)
            continue

        logger.info(
            "Backfilling %s -> %s (%d targets)",
            base,
            ", ".join(targets_needed),
            len(targets_needed),
        )

        try:
            count = await _backfill_multi_target(base, targets_needed)
            total += count
        except Exception:
            logger.exception("Error during backfill for base %s", base)

    logger.info("Preset currency backfill finished: %d total rows inserted", total)
