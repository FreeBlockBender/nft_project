"""
daily_ml_run.py

Daily ML pipeline orchestrator. Designed to run once per day after the
data import scripts have completed.

What it does:
  1. Retrains the XGBoost model on all available data (no CV, fast mode)
  2. Generates buy/sell signals for the latest date
  3. Sends a Telegram notification with top BUY signals to the monitoring chat

Usage:
    python scripts/daily_ml_run.py [--skip-train] [--dry-run]

Flags:
    --skip-train   Use the existing saved model instead of retraining.
                   Useful if you only want the daily prediction without the
                   cost of a full retrain (e.g. run retrain weekly via cron).
    --dry-run      Run the full pipeline but skip the Telegram notification.

Configuration (read from .env):
    ML_HORIZON          Forward return horizon in days  (default: 14)
    ML_THRESHOLD        BUY/SELL threshold as fraction  (default: 0.10)
    ML_MIN_CONFIDENCE   Minimum signal confidence shown (default: 0.60)
    ML_TOP_N            Max signals in Telegram message (default: 15)
    ML_LABEL            'binary' or '3class'            (default: binary)
    ML_MIN_DAYS         Min price days per collection   (default: 60)
    ML_MODEL_PATH       Path to save/load .pkl model    (default: data/ml_model.pkl)
"""

import argparse
import asyncio
import logging
import os
import sys
import time
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.config import load_config
from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
from app.ml.feature_pipeline import build_feature_dataframe
from app.ml.label_generator import add_labels
from app.ml.model import (
    DEFAULT_MODEL_PATH,
    load_model,
    predict_signals,
    save_model,
    train_final_model,
    walk_forward_cv,
)
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_ml_config() -> dict:
    """Read ML-specific settings from .env (with sensible defaults)."""
    config = load_config()
    return {
        "horizon":        int(config.get("ML_HORIZON")        or 14),
        "threshold":      float(config.get("ML_THRESHOLD")    or 0.10),
        "min_confidence": float(config.get("ML_MIN_CONFIDENCE") or 0.60),
        "top_n":          int(config.get("ML_TOP_N")          or 15),
        "label":          str(config.get("ML_LABEL")          or "binary"),
        "min_days":       int(config.get("ML_MIN_DAYS")        or 60),
        "model_path":     str(config.get("ML_MODEL_PATH")      or DEFAULT_MODEL_PATH),
    }


def _format_telegram_message(signals, ml_cfg: dict) -> str:
    """Format signal results as a Markdown Telegram message."""
    import numpy as np
    label_col   = "signal"
    min_conf    = ml_cfg["min_confidence"]
    top_n       = ml_cfg["top_n"]
    today_str   = datetime.utcnow().strftime("%Y-%m-%d")

    buy_signals = signals[
        (signals[label_col] == "BUY") &
        (signals["confidence"] >= min_conf)
    ].head(top_n)

    total = len(signals)
    n_buy = (signals[label_col] == "BUY").sum()
    n_hold = (signals[label_col] == "HOLD").sum()
    n_sell = (signals[label_col] == "SELL").sum() if "SELL" in signals[label_col].values else 0

    lines = [
        f"*NFT ML Signals* | {today_str}",
        f"Horizon: {ml_cfg['horizon']}d | Threshold: {ml_cfg['threshold']:.0%}",
        f"Total collections: {total} | BUY: {n_buy} | HOLD: {n_hold}" +
        (f" | SELL: {n_sell}" if n_sell > 0 else ""),
        f"\n*Top BUY signals (conf \u2265 {min_conf:.0%}): {len(buy_signals)}*\n",
    ]

    if buy_signals.empty:
        lines.append("_No high-confidence BUY signals today._")
    else:
        for rank, (_, row) in enumerate(buy_signals.iterrows(), start=1):
            cid       = str(row.get("collection_identifier", "N/A"))[:35]
            chain     = str(row.get("chain", ""))
            fn        = row.get("floor_native")
            fusd      = row.get("floor_usd")
            conf      = row.get("confidence", 0)
            price     = (f"{fn:.4f}" if fn else "N/A") + (f" (${fusd:,.0f})" if fusd else "")
            top_feat  = row.get("top_features") or ""
            lines.append(f"{rank}\\. `{cid}` \\({chain}\\): {price} | conf: {conf:.1%}")
            if top_feat:
                lines.append(f"   _\u21b3 {top_feat}_")

    return "\n".join(lines)


async def _notify(message: str, chat_id: str):
    await send_telegram_message(message, chat_id, parse_mode="MarkdownV2")


async def _notify_error(message: str, chat_id: str):
    await send_telegram_message(chat_id, message)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Daily NFT ML pipeline")
    p.add_argument("--skip-train", action="store_true",
                   help="Skip retraining and load existing model")
    p.add_argument("--dry-run", action="store_true",
                   help="Don't send Telegram notification")
    p.add_argument("--with-cv", action="store_true",
                   help="Run walk-forward CV during training (slower but informative)")
    return p.parse_args()


def main():
    setup_logging()
    args   = parse_args()
    ml_cfg = _get_ml_config()
    chat_id = get_monitoring_chat_id()
    label_col = "label_binary" if ml_cfg["label"] == "binary" else "label_3class"
    start_ts = time.time()

    logging.info("=" * 60)
    logging.info("Daily ML run started at %s", datetime.utcnow().isoformat())
    logging.info("Config: %s", ml_cfg)
    logging.info("=" * 60)

    # ── Step 1: Build feature dataframe ─────────────────────────
    # In prediction-only mode (--skip-train), load just the last 280 calendar
    # days per collection. This cuts peak RAM from ~1.8 GB to ~250 MB, making
    # the script safe on servers with <1 GB RAM.
    # In training mode, load full history so labels can be computed.
    lookback = 280 if args.skip_train else None
    pred_min_days = 20  # in prediction mode allow recently-listed collections

    try:
        logging.info(
            "[1/4] Building feature dataframe (mode=%s) ...",
            "predict-only (280d lookback)" if lookback else "full-history (training)",
        )
        conn = get_db_connection()
        df = build_feature_dataframe(
            conn,
            min_days=pred_min_days if lookback else ml_cfg["min_days"],
            lookback_days=lookback,
        )
        conn.close()

        if df.empty:
            raise RuntimeError("Feature dataframe is empty.")

        logging.info(
            "[1/4] Done. %d rows, %d collections, %s -> %s",
            len(df), df["collection_identifier"].nunique(),
            df["date"].min().date(), df["date"].max().date(),
        )
    except Exception as e:
        msg = f"[ML daily run] FAILED at feature pipeline:\n{e}"
        logging.error(msg)
        if not args.dry_run:
            asyncio.run(_notify_error(msg, chat_id))
        sys.exit(1)

    # ── Step 2: Train or load model ──────────────────────────────
    if args.skip_train:
        try:
            logging.info("[2/4] Loading existing model from %s ...", ml_cfg["model_path"])
            model, feature_names = load_model(ml_cfg["model_path"])
        except FileNotFoundError:
            logging.warning("[2/4] No saved model found — forcing retrain.")
            args.skip_train = False

    if not args.skip_train:
        try:
            df_labeled = add_labels(
                df,
                horizon_days=ml_cfg["horizon"],
                buy_threshold=ml_cfg["threshold"],
                sell_threshold=ml_cfg["threshold"],
            )

            if args.with_cv:
                logging.info("[2/4] Running walk-forward CV ...")
                cv = walk_forward_cv(df_labeled, label_col=label_col, n_splits=4)
                if cv:
                    logging.info(
                        "[2/4] CV: Precision=%.3f Recall=%.3f AUC=%.3f",
                        cv["mean_precision"], cv["mean_recall"], cv["mean_auc"],
                    )

            logging.info("[2/4] Training final model ...")
            model, feature_names = train_final_model(df_labeled, label_col=label_col)
            save_model(model, feature_names, path=ml_cfg["model_path"])
            logging.info("[2/4] Model saved to %s", ml_cfg["model_path"])

        except Exception as e:
            msg = f"[ML daily run] FAILED at training:\n{traceback.format_exc()}"
            logging.error(msg)
            if not args.dry_run:
                asyncio.run(_notify_error(msg, chat_id))
            sys.exit(1)

    # ── Step 3: Generate signals ─────────────────────────────────
    try:
        logging.info("[3/4] Generating signals ...")
        signals = predict_signals(model, df, label_col=label_col)

        if signals.empty:
            raise RuntimeError("No signals produced.")

        n_buy  = (signals["signal"] == "BUY").sum()
        n_conf = (
            (signals["signal"] == "BUY") &
            (signals["confidence"] >= ml_cfg["min_confidence"])
        ).sum()
        logging.info(
            "[3/4] Signals generated: %d collections | BUY=%d | high-conf BUY=%d",
            len(signals), n_buy, n_conf,
        )
    except Exception as e:
        msg = f"[ML daily run] FAILED at prediction:\n{e}"
        logging.error(msg)
        if not args.dry_run:
            asyncio.run(_notify_error(msg, chat_id))
        sys.exit(1)

    # ── Step 4: Send Telegram notification ───────────────────────
    elapsed = round(time.time() - start_ts, 1)
    logging.info("[4/4] Sending Telegram notification (dry_run=%s) ...", args.dry_run)

    if not args.dry_run:
        try:
            msg = _format_telegram_message(signals, ml_cfg)
            asyncio.run(_notify(msg, chat_id))
            logging.info("[4/4] Telegram message sent.")
        except Exception as e:
            logging.error("[4/4] Telegram notification failed: %s", e)

    logging.info("Daily ML run completed in %.1f seconds.", elapsed)


if __name__ == "__main__":
    main()
