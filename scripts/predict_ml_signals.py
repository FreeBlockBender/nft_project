"""
predict_ml_signals.py

Generate buy/sell/hold signals for all tracked NFT collections using the trained model.

Usage:
    python scripts/predict_ml_signals.py [--date YYYY-MM-DD] [--top-n 20]
                                          [--label binary|3class] [--model-path PATH]
                                          [--min-confidence 0.60] [--telegram]

Output:
    - Prints a ranked signal table to stdout
    - Optionally sends top BUY signals to the Telegram drafts/channel chat
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
from app.ml.feature_pipeline import build_feature_dataframe
from app.ml.model import (
    DEFAULT_MODEL_PATH,
    load_model,
    predict_signals,
)
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id


def parse_args():
    p = argparse.ArgumentParser(description="Predict NFT buy/sell signals")
    p.add_argument("--date",           type=str,   default=None,        help="As-of date YYYY-MM-DD (default: latest in DB)")
    p.add_argument("--top-n",          type=int,   default=20,          help="Number of top BUY signals to show (default: 20)")
    p.add_argument("--label",          type=str,   default="binary",    choices=["binary", "3class"])
    p.add_argument("--model-path",     type=str,   default=DEFAULT_MODEL_PATH)
    p.add_argument("--min-confidence", type=float, default=0.55,        help="Minimum confidence to include in output (default: 0.55)")
    p.add_argument("--min-days",       type=int,   default=60,          help="Min price days required per collection (default: 60)")
    p.add_argument("--telegram",       action="store_true",             help="Send top signals to Telegram monitoring chat")
    return p.parse_args()


def _format_signal_table(signals_df, top_n: int, min_confidence: float) -> str:
    """Format prediction results as a readable table string."""
    label_col = "signal"

    buy_signals = signals_df[
        (signals_df[label_col] == "BUY") &
        (signals_df["confidence"] >= min_confidence)
    ].head(top_n)

    lines = [
        f"NFT ML Signals | {signals_df['date'].max().date() if 'date' in signals_df.columns else 'N/A'}",
        f"BUY signals (confidence >= {min_confidence:.0%}): {len(buy_signals)}",
        "",
    ]

    if buy_signals.empty:
        lines.append("No BUY signals above confidence threshold.")
        return "\n".join(lines)

    lines.append(f"{'#':<3} {'Collection':<40} {'Chain':<10} {'Floor (native)':<16} {'Floor USD':<12} {'Conf':>6}")
    lines.append("-" * 95)

    for rank, (_, row) in enumerate(buy_signals.iterrows(), start=1):
        floor_native = f"{row.get('floor_native', 0):.4f}" if row.get("floor_native") else "N/A"
        floor_usd = f"${row.get('floor_usd', 0):,.2f}" if row.get("floor_usd") else "N/A"
        cid = str(row.get("collection_identifier", ""))[:38]
        chain = str(row.get("chain", ""))[:9]
        conf = f"{row.get('confidence', 0):.1%}"
        lines.append(f"{rank:<3} {cid:<40} {chain:<10} {floor_native:<16} {floor_usd:<12} {conf:>6}")
        top_feat = row.get("top_features")
        if top_feat:
            lines.append(f"    >> {top_feat}")

    return "\n".join(lines)


def _esc_html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_telegram_message(signals_df, top_n: int, min_confidence: float) -> str:
    """Format a structured HTML Telegram message with top BUY signals."""
    buy_signals = signals_df[
        (signals_df["signal"] == "BUY") &
        (signals_df["confidence"] >= min_confidence)
    ].head(top_n)

    as_of = signals_df["date"].max().date() if "date" in signals_df.columns else "N/A"
    total = len(signals_df)
    n_buy = (signals_df["signal"] == "BUY").sum()
    n_hold = (signals_df["signal"] == "HOLD").sum() if "HOLD" in signals_df["signal"].values else 0

    lines = [
        f"\U0001f916 <b>NFT ML Signals</b> | {as_of}",
        f"Tracked: {total} | BUY: {n_buy} | HOLD: {n_hold}",
        "",
        f"<b>\U0001f4c8 Top BUY signals (conf \u2265 {min_confidence:.0%})</b>  [{len(buy_signals)} found]",
        "",
    ]

    if buy_signals.empty:
        lines.append("<i>No high-confidence BUY signals today.</i>")
    else:
        for rank, (_, row) in enumerate(buy_signals.iterrows(), start=1):
            slug     = _esc_html(str(row.get("slug") or "")[:40])
            cid      = _esc_html(str(row.get("collection_identifier", "N/A"))[:35])
            chain    = _esc_html(str(row.get("chain", "")))
            fn       = row.get("floor_native")
            fusd     = row.get("floor_usd")
            conf     = row.get("confidence", 0)
            top_feat = _esc_html(row.get("top_features") or "")

            display      = slug if slug else cid
            price_native = f"{fn:.4f}" if fn else "N/A"
            price_usd    = f"${fusd:,.0f}" if fusd else ""
            price_str    = f"{price_native}  {price_usd}".strip() if price_usd else price_native

            lines.append(f"{rank}. <b>{display}</b>  <i>({chain})</i>")
            lines.append(f"   Floor: <code>{_esc_html(price_str)}</code>  |  conf: <b>{conf:.1%}</b>")
            if slug and cid and slug != cid:
                lines.append(f"   <i>id: {cid}</i>")
            if top_feat:
                lines.append(f"   \u21b3 <i>{top_feat}</i>")
            lines.append("")

    return "\n".join(lines)


def main():
    setup_logging()
    args = parse_args()

    label_col = "label_binary" if args.label == "binary" else "label_3class"

    logging.info("Loading model from %s ...", args.model_path)
    try:
        model, feature_names = load_model(args.model_path)
    except FileNotFoundError as e:
        logging.error("%s\nRun scripts/train_ml_model.py first.", e)
        sys.exit(1)

    logging.info("Building feature dataframe ...")
    conn = get_db_connection()
    try:
        df = build_feature_dataframe(conn, min_days=args.min_days)
    finally:
        conn.close()

    if df.empty:
        logging.error("Feature dataframe is empty. Aborting.")
        sys.exit(1)

    as_of = args.date or df["date"].max().strftime("%Y-%m-%d")
    logging.info("Generating signals as of %s ...", as_of)

    signals = predict_signals(model, df, label_col=label_col, as_of_date=as_of)

    if signals.empty:
        logging.warning("No signals generated.")
        sys.exit(0)

    # ── Print summary ─────────────────────────────────────────────
    table = _format_signal_table(signals, top_n=args.top_n, min_confidence=args.min_confidence)
    print("\n" + table + "\n")

    # ── Full distribution ─────────────────────────────────────────
    if "signal" in signals.columns:
        dist = signals["signal"].value_counts().to_dict()
        logging.info("Signal distribution: %s", dist)

    # ── Optional Telegram notification ───────────────────────────
    if args.telegram:
        msg = _format_telegram_message(signals, top_n=args.top_n, min_confidence=args.min_confidence)
        chat_id = get_monitoring_chat_id()
        logging.info("Sending signals to Telegram chat %s ...", chat_id)
        asyncio.run(send_telegram_message(msg, chat_id, parse_mode="HTML"))
        logging.info("Telegram message sent.")

    logging.info("Prediction complete.")


if __name__ == "__main__":
    main()
