"""Trend analysis and buy/sell suggestions based on moving averages."""

from bot.config import SUGGESTION_THRESHOLD_PCT


def get_suggestion(current_rate: float, history: list[dict]) -> tuple[str, str]:
    """Analyze trend and return (action, reason).

    Args:
        current_rate: The current exchange rate.
        history: List of dicts with "rate" and "fetched_at" keys,
                 ordered by fetched_at DESC (most recent first).

    Returns:
        Tuple of (action, reason) where action is "BUY", "SELL", or "HOLD"
        and reason is a Chinese explanation string.

    Logic:
        - Compute SMA-7 and SMA-14 from history
        - pct_from_sma7 = (current_rate - sma7) / sma7 * 100
        - If pct < -threshold and sma7 < sma14 → BUY
        - If pct > +threshold and sma7 > sma14 → SELL
        - Otherwise → HOLD
    """
    if len(history) < 7:
        return ("HOLD", "数据不足，暂无建议")

    # SMA-7: average of the 7 most recent rates
    sma7 = sum(h["rate"] for h in history[:7]) / 7

    # SMA-14: average of the 14 most recent rates (use what's available if < 14)
    sma14_entries = history[:14]
    sma14 = sum(h["rate"] for h in sma14_entries) / len(sma14_entries)

    pct_from_sma7 = (current_rate - sma7) / sma7 * 100

    if pct_from_sma7 < -SUGGESTION_THRESHOLD_PCT and sma7 < sma14:
        return ("BUY", "目标货币低于均线且处于下行趋势，可能是换汇好时机")

    if pct_from_sma7 > SUGGESTION_THRESHOLD_PCT and sma7 > sma14:
        return ("SELL", "目标货币高于均线且处于上行趋势，可考虑持有")

    return ("HOLD", "汇率接近均线，无明显趋势")
