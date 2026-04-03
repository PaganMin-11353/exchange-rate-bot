"""LightGBM prediction pipeline for exchange rate forecasting."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import lightgbm as lgb
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator, EMAIndicator
from ta.volatility import BollingerBands

from bot import database
from bot.config import TZ

logger = logging.getLogger(__name__)

MODELS_DIR = "models"

LGB_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "verbose": -1,
}


def _model_path(base: str, target: str) -> str:
    return os.path.join(MODELS_DIR, f"{base}_{target}.txt")


def _meta_path(base: str, target: str) -> str:
    return os.path.join(MODELS_DIR, f"{base}_{target}_meta.json")


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build technical indicator features from a rate DataFrame.

    Input df has columns: ['date', 'rate'] (sorted by date ASC).
    Output df has the original columns plus all feature columns.
    Uses the `ta` library for Close-based indicators.
    """
    df = df.copy()
    close = df["rate"]

    # Percentage returns
    df["return_1d"] = close.pct_change(1) * 100
    df["return_3d"] = close.pct_change(3) * 100
    df["return_5d"] = close.pct_change(5) * 100
    df["return_10d"] = close.pct_change(10) * 100
    df["return_20d"] = close.pct_change(20) * 100

    # RSI
    rsi = RSIIndicator(close=close, window=14)
    df["rsi_14"] = rsi.rsi()

    # MACD
    macd = MACD(close=close)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # Simple Moving Averages
    df["sma_7"] = SMAIndicator(close=close, window=7).sma_indicator()
    df["sma_14"] = SMAIndicator(close=close, window=14).sma_indicator()
    df["sma_30"] = SMAIndicator(close=close, window=30).sma_indicator()

    # Exponential Moving Averages
    df["ema_7"] = EMAIndicator(close=close, window=7).ema_indicator()
    df["ema_14"] = EMAIndicator(close=close, window=14).ema_indicator()

    # Rate vs SMA (% deviation)
    df["rate_vs_sma7"] = (close - df["sma_7"]) / df["sma_7"] * 100
    df["rate_vs_sma14"] = (close - df["sma_14"]) / df["sma_14"] * 100

    # Bollinger Bands
    bb = BollingerBands(close=close, window=20)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    bb_mid = SMAIndicator(close=close, window=20).sma_indicator()
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_mid

    # Calendar features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_of_month"] = df["date"].dt.day
    df["month"] = df["date"].dt.month

    return df


def _get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Return the list of feature column names (everything except date, rate, and target)."""
    exclude = {"date", "rate", "target"}
    return [c for c in df.columns if c not in exclude]


def _load_history_df(base: str, target: str) -> pd.DataFrame | None:
    """Load rate history into a date-sorted DataFrame."""
    # Get a large number of rows (all available data)
    history = database.get_rate_history(base, target, limit=0)
    if not history:
        return None

    df = pd.DataFrame(history)
    df = df.assign(date=pd.to_datetime(df["fetched_at"]))
    df = df[["date", "rate"]].sort_values("date").reset_index(drop=True)

    # Deduplicate by date (keep last entry per day)
    df = df.assign(date_only=df["date"].dt.date)
    df = df.drop_duplicates(subset="date_only", keep="last")
    df = df.assign(date=pd.to_datetime(df["date_only"]))
    df = df[["date", "rate"]].reset_index(drop=True)

    return df


def train_model(base: str, target: str) -> dict | None:
    """Train a LightGBM model for the given currency pair.

    Returns metrics dict {"direction_accuracy": float, "rmse": float} or None
    if insufficient data.
    """
    df = _load_history_df(base, target)
    if df is None:
        logger.info("No history data for %s/%s, skipping training", base, target)
        return None

    df = build_features(df)

    # Target variable: next day's rate
    df["target"] = df["rate"].shift(-1)

    # Drop NaN rows (from feature computation and target shift)
    df = df.dropna().reset_index(drop=True)

    if len(df) < 60:
        logger.info(
            "Insufficient data for %s/%s: %d rows (need 60)",
            base, target, len(df),
        )
        return None

    feature_cols = _get_feature_columns(df)

    # Train/test split: last 14 rows as test
    train_df = df.iloc[:-14]
    test_df = df.iloc[-14:]

    X_train = train_df[feature_cols]
    y_train = train_df["target"]
    X_test = test_df[feature_cols]
    y_test = test_df["target"]

    train_data = lgb.Dataset(X_train, label=y_train)
    valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

    callbacks = [
        lgb.early_stopping(stopping_rounds=10),
        lgb.log_evaluation(period=0),  # suppress logging
    ]

    model = lgb.train(
        LGB_PARAMS,
        train_data,
        num_boost_round=500,
        valid_sets=[valid_data],
        callbacks=callbacks,
    )

    # Evaluate
    predictions = model.predict(X_test)
    rmse = float(((predictions - y_test.values) ** 2).mean() ** 0.5)

    # Direction accuracy: did we predict the right direction of change?
    actual_direction = (y_test.values - test_df["rate"].values) > 0
    pred_direction = (predictions - test_df["rate"].values) > 0
    direction_accuracy = float((actual_direction == pred_direction).mean())

    # Save model atomically (write to temp, then rename) to avoid
    # race conditions with concurrent predict_next_days reads
    os.makedirs(MODELS_DIR, exist_ok=True)
    tmp_model = _model_path(base, target) + ".tmp"
    model.save_model(tmp_model)
    os.replace(tmp_model, _model_path(base, target))

    # Save metadata (feature columns + metrics)
    meta = {
        "feature_columns": feature_cols,
        "direction_accuracy": direction_accuracy,
        "rmse": rmse,
        "trained_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
    }
    tmp_meta = _meta_path(base, target) + ".tmp"
    with open(tmp_meta, "w") as f:
        json.dump(meta, f, indent=2)
    os.replace(tmp_meta, _meta_path(base, target))

    logger.info(
        "Trained model for %s/%s: RMSE=%.6f, direction_accuracy=%.2f%%",
        base, target, rmse, direction_accuracy * 100,
    )
    return {"direction_accuracy": direction_accuracy, "rmse": rmse}


def predict_next_days(base: str, target: str, days: int = 3) -> list[dict] | None:
    """Predict the next N days' rates using recursive forecasting.

    Returns list of {"date": str, "rate": float, "change_pct": float} or None.
    """
    model_file = _model_path(base, target)
    meta_file = _meta_path(base, target)

    # Load or train model
    if not os.path.exists(model_file):
        result = train_model(base, target)
        if result is None:
            return None

    if not os.path.exists(model_file):
        return None

    model = lgb.Booster(model_file=model_file)

    # Load feature columns from metadata
    if not os.path.exists(meta_file):
        logger.warning("No metadata for %s/%s, cannot predict", base, target)
        return None

    with open(meta_file) as f:
        meta = json.load(f)
    feature_cols = meta["feature_columns"]

    # Load latest rate history and build features
    df = _load_history_df(base, target)
    if df is None:
        return None

    current_rate = df["rate"].iloc[-1]
    last_date = df["date"].iloc[-1]

    predictions = []
    for i in range(1, days + 1):
        # Build features for current state
        feat_df = build_features(df)
        feat_df = feat_df.dropna().reset_index(drop=True)

        if feat_df.empty:
            logger.warning("Empty feature df for %s/%s at day %d", base, target, i)
            break

        # Use the last row's features to predict next day
        last_features = feat_df[feature_cols].iloc[[-1]]
        pred_rate = float(model.predict(last_features)[0])

        pred_date = last_date + timedelta(days=i)
        change_pct = (pred_rate - current_rate) / current_rate * 100

        predictions.append({
            "date": pred_date.strftime("%m-%d"),
            "rate": pred_rate,
            "change_pct": change_pct,
        })

        # Append prediction to df for recursive forecasting
        new_row = pd.DataFrame([{"date": pred_date, "rate": pred_rate}])
        df = pd.concat([df, new_row], ignore_index=True)

    return predictions if predictions else None


def get_model_confidence(base: str, target: str) -> tuple[str, float | None]:
    """Return confidence label and direction accuracy.

    Returns ("高"/"中"/"低"/"未知", accuracy_or_None)
    """
    meta_file = _meta_path(base, target)
    if not os.path.exists(meta_file):
        return ("未知", None)

    with open(meta_file) as f:
        meta = json.load(f)

    accuracy = meta.get("direction_accuracy")
    if accuracy is None:
        return ("未知", None)

    if accuracy >= 0.65:
        label = "高"
    elif accuracy >= 0.55:
        label = "中"
    else:
        label = "低"

    return (label, accuracy)


def _retrain_all_sync() -> None:
    """Retrain models for all active currency pairs, serially (blocking)."""
    pairs = database.get_all_active_pairs()
    if not pairs:
        logger.info("No active pairs, skipping model retrain")
        return

    logger.info("Retraining models for %d currency pairs", len(pairs))
    success = 0
    failed = 0

    for base, target in pairs:
        try:
            result = train_model(base, target)
            if result is not None:
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
            logger.exception("Error training model for %s/%s", base, target)

    logger.info(
        "Model retrain complete: %d success, %d failed/skipped", success, failed
    )


async def retrain_all_models() -> None:
    """Retrain all models in a thread to avoid blocking the event loop."""
    await asyncio.to_thread(_retrain_all_sync)
