"""Message formatting utilities for exchange rate notifications."""

from datetime import datetime, timedelta

from bot.config import TZ
from bot import database


def compute_change_and_avg(base: str, target: str) -> tuple[float | None, float | None]:
    """Compute 24h percentage change and 7-day average from rate history."""
    history = database.get_rate_history(base, target, limit=30)
    if not history:
        return None, None

    current_rate = history[0]["rate"]

    change_24h = None
    if len(history) >= 2:
        yesterday_rate = history[1]["rate"]
        if yesterday_rate != 0:
            change_24h = (current_rate - yesterday_rate) / yesterday_rate * 100

    entries_for_avg = history[:7]
    if entries_for_avg:
        avg_7d = sum(e["rate"] for e in entries_for_avg) / len(entries_for_avg)
    else:
        avg_7d = None

    return change_24h, avg_7d


def _suggestion_label(suggestion: tuple[str, str] | None) -> str:
    """Convert suggestion tuple to short Chinese label."""
    if suggestion is None:
        return "观望"
    action = suggestion[0]
    if action == "BUY":
        return "买入"
    elif action == "SELL":
        return "卖出"
    return "观望"


def _prediction_trend(prediction_summary: str | None) -> str:
    """Extract a short trend word from prediction summary."""
    if not prediction_summary:
        return "暂无"
    parts = prediction_summary.replace(" (3天)", "").split(" → ")
    if len(parts) >= 2:
        try:
            first = float(parts[0])
            last = float(parts[-1])
            pct = (last - first) / first * 100
            if pct > 0.1:
                return "微涨"
            elif pct < -0.1:
                return "微跌"
            return "平稳"
        except ValueError:
            pass
    return "暂无"


def _prediction_values(prediction_summary: str | None) -> list[str]:
    """Extract 3 rate values from prediction summary."""
    if not prediction_summary:
        return []
    parts = prediction_summary.replace(" (3天)", "").split(" → ")
    return parts


def _build_prediction_table(
    home_currency: str,
    targets: list[dict],
) -> str:
    """Build the monospace prediction table."""
    # Collect prediction data
    currency_names = []
    pred_values: list[list[str]] = []  # [day][currency]
    trends = []

    for t in targets:
        currency_names.append(t["target_currency"])
        values = _prediction_values(t.get("prediction_summary"))
        if len(values) == 3:
            pred_values.append(values)
            trends.append(_prediction_trend(t.get("prediction_summary")))
        else:
            pred_values.append(["--", "--", "--"])
            trends.append("暂无")

    if not currency_names:
        return ""

    # Column width based on data values (all ASCII)
    col_w = max(len(v) for vals in pred_values for v in vals)
    col_w = max(col_w, max(len(c) for c in currency_names))
    col_w = max(col_w, 6)

    def _rpad(text: str, width: int) -> str:
        """Right-align text accounting for CJK double-width chars."""
        display_w = sum(2 if ord(c) > 0x7F else 1 for c in text)
        return " " * (width - display_w) + text

    # Row label width: "05-06" = 5 chars, "趋势" = 4 display chars
    label_w = 5

    # Build header
    header = " " * label_w + " "
    for name in currency_names:
        header += _rpad(name, col_w) + "  "

    # Build date rows
    today = datetime.now(TZ).date()
    rows = []
    for day_idx in range(3):
        date = today + timedelta(days=day_idx + 1)
        date_str = date.strftime("%m-%d")
        row = date_str + " "
        for curr_idx in range(len(currency_names)):
            val = pred_values[curr_idx][day_idx] if day_idx < len(pred_values[curr_idx]) else "--"
            row += _rpad(val, col_w) + "  "
        rows.append(row)

    # Build trend row — "趋势" is 4 display-width, pad to label_w
    trend_row = "趋势" + " " * (label_w - 4 + 1)
    for trend in trends:
        trend_row += _rpad(trend, col_w) + "  "

    lines = [header] + rows + [trend_row]
    return "\n".join(lines)


def _build_advice(home_currency: str, targets: list[dict]) -> str:
    """Build the bold advice line based on suggestions."""
    advices = []
    for t in targets:
        suggestion = t.get("suggestion")
        if suggestion is None:
            continue
        action = suggestion[0]
        target = t["target_currency"]
        if action == "BUY":
            advices.append(f"适合用{home_currency}换{target}")
        elif action == "SELL":
            advices.append(f"适合用{target}换{home_currency}")

    if not advices:
        return "*建议: 暂无明显换汇机会*"
    return f"*建议: {', '.join(advices)}*"


def format_rate_message(
    home_currency: str,
    targets: list[dict],
    show_prediction: bool = True,
    show_suggestion: bool = True,
) -> str:
    """Format the compact rate notification message.

    Uses Telegram MarkdownV2 for bold title and advice.
    Prediction table uses monospace code block.
    """
    today_str = datetime.now(TZ).strftime("%m-%d")

    # Bold title
    lines = [f"*\U0001f4ca {today_str} {home_currency} 汇率*", ""]

    # Rate lines
    for t in targets:
        target = t["target_currency"]
        rate = t["rate"]
        change_24h = t.get("change_24h")

        if change_24h is not None:
            arrow = "\u25b2" if change_24h >= 0 else "\u25bc"
            sign = "+" if change_24h > 0 else ""
            change_str = f"{arrow}{sign}{change_24h:.2f}%"
        else:
            change_str = "\u002d\u002d"

        suggestion_str = ""
        if show_suggestion:
            label = _suggestion_label(t.get("suggestion"))
            suggestion_str = f" {label}"

        lines.append(f"{target} {rate:.4f} {change_str}{suggestion_str}")

    # Prediction table
    if show_prediction:
        table = _build_prediction_table(home_currency, targets)
        if table:
            lines.append("")
            lines.append("3日预测:")
            lines.append(f"```\n{table}\n```")

    # Bold advice
    if show_suggestion:
        lines.append("")
        lines.append(_build_advice(home_currency, targets))

    return "\n".join(lines)
