# Phase 1: Skeleton — Code Review

**Date:** 2026-04-04
**Verdict:** FAIL → Fixed → Committed

## Issues Found

### Critical (fixed before commit)
1. **PRAGMA journal_mode=WAL inside executescript is unreliable** — moved to standalone `conn.execute()` call
2. **PRAGMA foreign_keys=ON is per-connection** — moved into `_connect()` context manager so it applies to every connection
3. **systemd service missing EnvironmentFile** — added `EnvironmentFile=/opt/exchange-rate-bot/.env`

### Important (fixed before commit)
4. **add_user_target not atomic** — two separate connections for check + insert; inlined into single connection with IntegrityError handling
5. **.gitignore missing patterns** — added `*.egg-info/`, `.env.*`, `!.env.example`, editor files

### Noted for later
- `rate_history` UNIQUE constraint on second-precision `fetched_at` may cause issues with daily data (addressed in Phase 2 by using date-only strings)
- Relative paths in `os.makedirs` — works with systemd WorkingDirectory, acceptable
