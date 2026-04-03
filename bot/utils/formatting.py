"""Message formatting utilities for exchange rate notifications."""

from datetime import datetime

from bot.config import TZ
from bot import database


def compute_change_and_avg(base: str, target: str) -> tuple[float | None, float | None]:
    """Compute 24h percentage change and 7-day average from rate history.

    Returns (change_24h_pct, avg_7d).
    - change_24h_pct: percentage change from ~24h ago to most recent, or None
    - avg_7d: mean of last 7 distinct day rates, or None
    """
    history = database.get_rate_history(base, target, days=30)
    if not history:
        return None, None

    # history is ordered by fetched_at DESC; index 0 is most recent
    current_rate = history[0]["rate"]

    # 24h change: find the entry closest to 24h ago
    change_24h = None
    if len(history) >= 2:
        yesterday_rate = history[1]["rate"]
        if yesterday_rate != 0:
            change_24h = (current_rate - yesterday_rate) / yesterday_rate * 100

    # 7d average: take up to 7 most recent entries
    entries_for_avg = history[:7]
    if entries_for_avg:
        avg_7d = sum(e["rate"] for e in entries_for_avg) / len(entries_for_avg)
    else:
        avg_7d = None

    return change_24h, avg_7d


def format_pair_line(
    home: str,
    target: str,
    rate: float,
    change_24h: float | None,
    avg_7d: float | None,
    suggestion: tuple[str, str] | None = None,
) -> str:
    """Format a single currency pair block within the notification message."""
    lines = [f"{home} \u2192 {target}: {rate:.4f}"]

    # 24h change
    if change_24h is not None:
        arrow = "\u25b2" if change_24h >= 0 else "\u25bc"
        sign = "+" if change_24h >= 0 else ""
        change_str = f"{arrow} {sign}{change_24h:.2f}%"
    else:
        change_str = "\u6682\u65e0\u6570\u636e"

    # 7d average
    if avg_7d is not None:
        avg_str = f"{avg_7d:.4f}"
    else:
        avg_str = "\u6682\u65e0\u6570\u636e"

    lines.append(f"  24h: {change_str}  |  7d avg: {avg_str}")

    # Buy/sell suggestion
    if suggestion is not None:
        action, reason = suggestion
        lines.append(f"  \U0001f4a1 \u5efa\u8bae: {action} \u2014 {reason}")
    else:
        lines.append("  \U0001f4a1 \u5efa\u8bae: \u6682\u65e0")

    return "\n".join(lines)


def format_rate_message(home_currency: str, targets: list[dict]) -> str:
    """Format the full rate notification message.

    Each target dict should have:
        - target_currency: str
        - rate: float
        - change_24h: float | None  (percentage)
        - avg_7d: float | None
    """
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")

    lines = [
        f"\U0001f4ca \u4eca\u65e5\u6c47\u7387 ({today_str})",
        "",
        f"\U0001f3e0 \u6301\u6709\u8d27\u5e01: {home_currency}",
        "",
    ]

    for t in targets:
        pair_block = format_pair_line(
            home_currency,
            t["target_currency"],
            t["rate"],
            t.get("change_24h"),
            t.get("avg_7d"),
            t.get("suggestion"),
        )
        lines.append(pair_block)
        lines.append("")

    lines.append("\u26a0\ufe0f \u4ee5\u4e0a\u4ec5\u4f9b\u53c2\u8003\uff0c\u4e0d\u6784\u6210\u6295\u8d44\u5efa\u8bae")

    return "\n".join(lines)
