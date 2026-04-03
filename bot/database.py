import sqlite3
from contextlib import contextmanager
from bot.config import DB_PATH


def initialize():
    """Create tables if they don't exist."""
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                username TEXT,
                home_currency TEXT NOT NULL DEFAULT 'SGD',
                interval_hours INTEGER NOT NULL DEFAULT 24,
                last_notified_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS user_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                target_currency TEXT NOT NULL,
                display_order INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, target_currency)
            );

            CREATE TABLE IF NOT EXISTS rate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                base_currency TEXT NOT NULL,
                target_currency TEXT NOT NULL,
                rate REAL NOT NULL,
                fetched_at TEXT DEFAULT (datetime('now')),
                UNIQUE(base_currency, target_currency, fetched_at)
            );

            CREATE INDEX IF NOT EXISTS idx_rate_history_pair_date
                ON rate_history(base_currency, target_currency, fetched_at);

            CREATE TABLE IF NOT EXISTS rate_cache (
                base_currency TEXT PRIMARY KEY,
                rates_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
        """)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ── User CRUD ──

def upsert_user(user_id: int, chat_id: int, username: str | None, home_currency: str = "SGD") -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO users (user_id, chat_id, username, home_currency)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   chat_id=excluded.chat_id,
                   username=excluded.username,
                   is_active=1""",
            (user_id, chat_id, username, home_currency),
        )


def get_user(user_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def update_user_home_currency(user_id: int, home_currency: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET home_currency=? WHERE user_id=?", (home_currency, user_id))


def update_user_interval(user_id: int, interval_hours: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET interval_hours=? WHERE user_id=?", (interval_hours, user_id))


def update_last_notified(user_id: int, timestamp: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET last_notified_at=? WHERE user_id=?", (timestamp, user_id))


def deactivate_user(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))


def get_active_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users WHERE is_active=1").fetchall()
        return [dict(r) for r in rows]


# ── User Targets CRUD ──

def set_user_targets(user_id: int, targets: list[str]) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM user_targets WHERE user_id=?", (user_id,))
        for i, target in enumerate(targets, 1):
            conn.execute(
                "INSERT INTO user_targets (user_id, target_currency, display_order) VALUES (?, ?, ?)",
                (user_id, target, i),
            )


def get_user_targets(user_id: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT target_currency FROM user_targets WHERE user_id=? ORDER BY display_order",
            (user_id,),
        ).fetchall()
        return [r["target_currency"] for r in rows]


def add_user_target(user_id: int, target_currency: str) -> bool:
    """Add a target. Returns False if already at max (3) or duplicate."""
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM user_targets WHERE user_id=?", (user_id,)
        ).fetchone()["cnt"]
        if count >= 3:
            return False
        try:
            conn.execute(
                "INSERT INTO user_targets (user_id, target_currency, display_order) VALUES (?, ?, ?)",
                (user_id, target_currency, count + 1),
            )
        except sqlite3.IntegrityError:
            return False
    return True


def remove_user_target(user_id: int, target_currency: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM user_targets WHERE user_id=? AND target_currency=?",
            (user_id, target_currency),
        )
        return cursor.rowcount > 0


# ── Rate History ──

def insert_rate(base: str, target: str, rate: float, fetched_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO rate_history (base_currency, target_currency, rate, fetched_at)
               VALUES (?, ?, ?, ?)""",
            (base, target, rate, fetched_at),
        )


def insert_rates_bulk(rows: list[tuple[str, str, float, str]]) -> None:
    with _connect() as conn:
        conn.executemany(
            """INSERT OR IGNORE INTO rate_history (base_currency, target_currency, rate, fetched_at)
               VALUES (?, ?, ?, ?)""",
            rows,
        )


def get_rate_history(base: str, target: str, days: int = 30) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """SELECT rate, fetched_at FROM rate_history
               WHERE base_currency=? AND target_currency=?
               ORDER BY fetched_at DESC LIMIT ?""",
            (base, target, days),
        ).fetchall()
        return [dict(r) for r in rows]


def get_distinct_base_currencies() -> list[str]:
    """Get all unique home currencies from active users."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT home_currency FROM users WHERE is_active=1"
        ).fetchall()
        return [r["home_currency"] for r in rows]


def get_all_active_pairs() -> list[tuple[str, str]]:
    """Get all unique (home_currency, target_currency) pairs from active users."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT DISTINCT u.home_currency, ut.target_currency
               FROM users u
               JOIN user_targets ut ON u.user_id = ut.user_id
               WHERE u.is_active=1""",
        ).fetchall()
        return [(r["home_currency"], r["target_currency"]) for r in rows]


def has_rate_history(base: str, target: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM rate_history WHERE base_currency=? AND target_currency=? LIMIT 1",
            (base, target),
        ).fetchone()
        return row is not None


# ── Rate Cache ──

def get_cached_rates(base: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT rates_json, fetched_at FROM rate_cache WHERE base_currency=?",
            (base,),
        ).fetchone()
        return dict(row) if row else None


def update_cache(base: str, rates_json: str, fetched_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO rate_cache (base_currency, rates_json, fetched_at)
               VALUES (?, ?, ?)
               ON CONFLICT(base_currency) DO UPDATE SET
                   rates_json=excluded.rates_json,
                   fetched_at=excluded.fetched_at""",
            (base, rates_json, fetched_at),
        )
