# Phase 2: Data Engine — Code Review

**Date:** 2026-04-04
**Verdict:** FAIL → Fixed → Committed

## Issues Found

### Critical (fixed before commit)
1. **`datetime.utcnow()` deprecated** — replaced with `datetime.now(timezone.utc)` throughout exchange_api.py

### Important (fixed before commit)
2. **Scheduler loops per-pair instead of per-base** — restructured to group by base currency, first call triggers fetch+cache, subsequent calls hit fresh cache
3. **`get_rate()` inserts ALL ~160 currencies into rate_history** — filtered to only PRESET_CURRENCIES + active user targets
4. **`date.today()` uses server local time, not UTC+8** — replaced with `datetime.now(TZ).date()`

### Moderate (fixed before commit)
5. **Background task reference not saved (GC risk)** — added `_background_tasks` set with `add_done_callback(discard)` pattern

### Noted
- First startup backfill takes several minutes for 10 currencies × 5 years
- `has_rate_history` check means partial backfills won't be retried
- httpx client created per-request (acceptable for low frequency)
