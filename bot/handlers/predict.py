"""Handler for /predict -- show 3-day exchange rate forecast."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot import database
from bot.services.predictor import predict_next_days, get_model_confidence

logger = logging.getLogger(__name__)


async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /predict [TARGET] -- show 3-day forecast.

    If TARGET is given, show detailed prediction for home -> TARGET.
    If not given, show predictions for all user's targets (brief).
    """
    user = update.effective_user
    db_user = database.get_user(user.id)

    if not db_user:
        await update.message.reply_text(
            "您还没有注册，请先使用 /start 进行初始化设置。"
        )
        return

    home = db_user["home_currency"]
    args = context.args

    if args:
        # Specific target requested -- detailed view
        target = args[0].upper()
        await _send_detailed_prediction(update, home, target)
    else:
        # No target -- show all user targets briefly
        targets = database.get_user_targets(user.id)
        if not targets:
            await update.message.reply_text(
                "您还没有设置跟踪目标货币，请使用 /settings 添加。"
            )
            return

        await _send_brief_predictions(update, home, targets)


async def _send_detailed_prediction(
    update: Update, home: str, target: str
) -> None:
    """Send detailed 3-day prediction for a single pair."""
    predictions = predict_next_days(home, target, days=3)

    if predictions is None:
        await update.message.reply_text(
            f"暂时无法生成 {home} -> {target} 的预测。\n"
            "可能是历史数据不足（需要至少60天），请稍后再试。"
        )
        return

    # Get current rate from the latest history
    history = database.get_rate_history(home, target, days=1)
    if history:
        current_rate = history[0]["rate"]
    else:
        current_rate = predictions[0]["rate"]  # fallback

    confidence_label, accuracy = get_model_confidence(home, target)

    lines = [f"📈 {home} → {target} 3日预测", ""]
    lines.append(f"当前: {current_rate:.4f}")

    for i, pred in enumerate(predictions, 1):
        sign = "+" if pred["change_pct"] >= 0 else ""
        lines.append(
            f"Day {i} ({pred['date']}): "
            f"{pred['rate']:.4f} ({sign}{pred['change_pct']:.2f}%)"
        )

    lines.append("")

    if accuracy is not None:
        lines.append(
            f"模型置信度: {confidence_label} (方向准确率 {accuracy * 100:.0f}%)"
        )
    else:
        lines.append(f"模型置信度: {confidence_label}")

    lines.append("方法: LightGBM + 技术指标")
    lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议")

    await update.message.reply_text("\n".join(lines))


async def _send_brief_predictions(
    update: Update, home: str, targets: list[str]
) -> None:
    """Send brief predictions for multiple targets."""
    lines = [f"📈 {home} 汇率预测 (3日)", ""]
    has_any = False

    for target in targets:
        predictions = predict_next_days(home, target, days=3)
        if predictions is None:
            lines.append(f"  {target}: 数据不足，暂无预测")
            continue

        has_any = True
        # Show just the 3-day prediction summary
        last_pred = predictions[-1]
        sign = "+" if last_pred["change_pct"] >= 0 else ""
        confidence_label, _ = get_model_confidence(home, target)
        lines.append(
            f"  {target}: {predictions[0]['rate']:.4f} → "
            f"{last_pred['rate']:.4f} ({sign}{last_pred['change_pct']:.2f}%) "
            f"[{confidence_label}]"
        )

    if has_any:
        lines.append("")
        lines.append("使用 /predict <货币> 查看详细预测")

    lines.append("")
    lines.append("⚠️ 仅供参考，不构成投资建议")

    await update.message.reply_text("\n".join(lines))
