# Phase 3: /start and /settings — Code Review

**Date:** 2026-04-04
**Verdict:** FAIL → Fixed → Committed

## Issues Found

### Critical (fixed before commit)
1. **`upsert_user` ON CONFLICT does not update home_currency** — reconfigure flow silently dropped new choice; added `home_currency=excluded.home_currency`
2. **`_trigger_backfill` silently swallows exceptions** — `lambda t: None` callback produces no log output; extracted `_log_backfill_error` callback

### Important (fixed before commit)
3. **Duplicated code between `_apply_new_home` and `_apply_new_home_text`** — extracted `_change_home_currency()` shared helper
4. **Duplicated `_interval_label` and `_trigger_backfill`** — moved to `bot/handlers/_common.py` shared module with `compute_new_targets()`

### Noted for Phase 7
- CallbackQueryHandlers have no pattern filters (defensive, not critical)
- No conversation timeout set
- `/start` reconfigure path shows hardcoded interval=24 in summary (cosmetic)
