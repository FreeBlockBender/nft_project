"""
Walk-forward P&L backtest for the NFT ML model.

This script measures economic performance, not just classification metrics:
  - builds the feature dataframe from the DB
  - generates forward-return labels
  - runs expanding-window walk-forward training/testing
  - opens BUY trades only on out-of-sample rows
  - enforces at most one active trade per collection/chain at a time
  - computes realized P&L from the forward return used by the label horizon

The result is a true out-of-sample signal backtest with equal-weight trades.
"""

import argparse
import logging
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
from app.ml.feature_pipeline import build_feature_dataframe
from app.ml.label_generator import add_labels
from app.ml.model import prepare_dataset, train_model, walk_forward_splits


def parse_args():
    parser = argparse.ArgumentParser(description="True P&L backtest for the NFT ML model")
    parser.add_argument("--horizon", type=int, default=14, help="Forward holding horizon in days")
    parser.add_argument("--threshold", type=float, default=0.10, help="BUY label threshold, default 10%%")
    parser.add_argument("--min-days", type=int, default=60, help="Minimum history per collection")
    parser.add_argument("--cv-splits", type=int, default=5, help="Walk-forward fold count")
    parser.add_argument("--min-confidence", type=float, default=0.60, help="Minimum BUY probability to open a trade")
    parser.add_argument("--top-n-per-day", type=int, default=0, help="Optional cap of BUY trades per day; 0 means uncapped")
    return parser.parse_args()


def _predict_buy_prob(model, x_test: pd.DataFrame) -> pd.Series:
    probs = model.predict_proba(x_test)
    if probs.ndim != 2 or probs.shape[1] < 2:
        raise ValueError("Binary model expected predict_proba with 2 columns")
    return pd.Series(probs[:, 1], index=x_test.index)


def _build_trade_candidates(test_df: pd.DataFrame, probabilities: pd.Series, min_confidence: float) -> pd.DataFrame:
    candidates = test_df.copy()
    candidates["buy_prob"] = probabilities
    candidates = candidates[candidates["buy_prob"] >= min_confidence].copy()
    if candidates.empty:
        return candidates
    candidates = candidates.sort_values(["date", "buy_prob"], ascending=[True, False]).reset_index(drop=True)
    return candidates


def _simulate_trades(candidates: pd.DataFrame, horizon_days: int, top_n_per_day: int = 0) -> tuple[list[dict], int]:
    trades = []
    next_available_by_asset: dict[tuple[str, str], pd.Timestamp] = {}
    skipped_overlap = 0

    if candidates.empty:
        return trades, skipped_overlap

    grouped = candidates.groupby("date", sort=True)
    for trade_date, day_rows in grouped:
        day_rows = day_rows.sort_values("buy_prob", ascending=False)
        if top_n_per_day > 0:
            day_rows = day_rows.head(top_n_per_day)

        for _, row in day_rows.iterrows():
            asset_key = (row["collection_identifier"], row["chain"])
            next_available = next_available_by_asset.get(asset_key)
            if next_available is not None and trade_date < next_available:
                skipped_overlap += 1
                continue

            if pd.isna(row["forward_ret"]):
                continue

            exit_date = trade_date + pd.Timedelta(days=horizon_days)
            next_available_by_asset[asset_key] = exit_date
            trades.append({
                "collection_identifier": row["collection_identifier"],
                "slug": row.get("slug"),
                "chain": row["chain"],
                "entry_date": trade_date,
                "exit_date": exit_date,
                "buy_prob": float(row["buy_prob"]),
                "forward_ret": float(row["forward_ret"]),
                "floor_native": row.get("floor_native"),
                "floor_usd": row.get("floor_usd"),
            })

    return trades, skipped_overlap


def _summarize_trades(trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "sum_units": 0.0,
            "pct_gt_10": 0.0,
            "pct_gt_20": 0.0,
            "pct_lt_minus10": 0.0,
            "pct_lt_minus20": 0.0,
        }

    rets = trades_df["forward_ret"]
    n = len(rets)
    return {
        "n_trades": n,
        "win_rate": (rets > 0).mean() * 100,
        "avg_return_pct": rets.mean() * 100,
        "median_return_pct": rets.median() * 100,
        "sum_units": rets.sum(),
        "pct_gt_10": (rets > 0.10).mean() * 100,
        "pct_gt_20": (rets > 0.20).mean() * 100,
        "pct_lt_minus10": (rets < -0.10).mean() * 100,
        "pct_lt_minus20": (rets < -0.20).mean() * 100,
    }


def main():
    setup_logging()
    args = parse_args()

    logging.info("=" * 70)
    logging.info("ML WALK-FORWARD P&L BACKTEST")
    logging.info(
        "horizon=%dd | label threshold=%.0f%% | min_confidence=%.0f%% | min_days=%d | cv_splits=%d | top_n_per_day=%s",
        args.horizon,
        args.threshold * 100,
        args.min_confidence * 100,
        args.min_days,
        args.cv_splits,
        args.top_n_per_day if args.top_n_per_day > 0 else "uncapped",
    )
    logging.info("=" * 70)

    conn = get_db_connection()
    try:
        df = build_feature_dataframe(conn, min_days=args.min_days)
    finally:
        conn.close()

    if df.empty:
        logging.error("Feature dataframe is empty. Aborting.")
        sys.exit(1)

    df = add_labels(
        df,
        horizon_days=args.horizon,
        buy_threshold=args.threshold,
        sell_threshold=args.threshold,
    )
    df = df.sort_values("date").reset_index(drop=True)

    x_all, y_all = prepare_dataset(df, label_col="label_binary")
    valid_idx = set(x_all.index)
    splits = list(walk_forward_splits(df, n_splits=args.cv_splits))
    if not splits:
        logging.error("No valid walk-forward splits produced.")
        sys.exit(1)

    all_trades = []
    fold_summaries = []
    total_skipped_overlap = 0

    for fold_number, (train_idx, test_idx) in enumerate(splits, start=1):
        tr = [ix for ix in train_idx if ix in valid_idx]
        te = [ix for ix in test_idx if ix in valid_idx]
        if len(tr) < 50 or len(te) < 10:
            logging.warning("Fold %d skipped due to insufficient rows after label filtering.", fold_number)
            continue

        x_train, y_train = x_all.loc[tr], y_all.loc[tr]
        x_test, y_test = x_all.loc[te], y_all.loc[te]
        test_df = df.loc[te].copy()

        val_cut = int(len(x_train) * 0.8)
        x_val = x_train.iloc[val_cut:]
        y_val = y_train.iloc[val_cut:]
        x_train_fit = x_train.iloc[:val_cut]
        y_train_fit = y_train.iloc[:val_cut]

        model = train_model(
            x_train_fit,
            y_train_fit,
            X_val=x_val,
            y_val=y_val,
            label_col="label_binary",
        )

        buy_prob = _predict_buy_prob(model, x_test)
        candidates = _build_trade_candidates(test_df, buy_prob, args.min_confidence)
        trades, skipped_overlap = _simulate_trades(candidates, args.horizon, args.top_n_per_day)
        total_skipped_overlap += skipped_overlap

        fold_trades = pd.DataFrame(trades)
        fold_summary = _summarize_trades(fold_trades)
        fold_summary.update({
            "fold": fold_number,
            "train_rows": len(tr),
            "test_rows": len(te),
            "candidates": len(candidates),
            "skipped_overlap": skipped_overlap,
            "test_start": test_df["date"].min().date(),
            "test_end": test_df["date"].max().date(),
        })
        fold_summaries.append(fold_summary)
        all_trades.extend(trades)

        logging.info(
            "Fold %d | Test %s→%s | candidates=%d | trades=%d | avg=%.2f%% | median=%.2f%% | win=%.1f%%",
            fold_number,
            fold_summary["test_start"],
            fold_summary["test_end"],
            fold_summary["candidates"],
            fold_summary["n_trades"],
            fold_summary["avg_return_pct"],
            fold_summary["median_return_pct"],
            fold_summary["win_rate"],
        )

    trades_df = pd.DataFrame(all_trades)
    overall = _summarize_trades(trades_df)

    print("\n" + "=" * 90)
    print("ML WALK-FORWARD P&L BACKTEST")
    print("=" * 90)
    print(f"Rows in feature dataframe: {len(df):,}")
    print(f"Collections: {df['collection_identifier'].nunique():,}")
    print(f"Date range: {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"Signal rule: BUY if predicted probability >= {args.min_confidence:.0%}")
    print(f"Holding period: {args.horizon} days")
    print(f"Per-collection overlap filter: enabled")
    if args.top_n_per_day > 0:
        print(f"Top-N cap per day: {args.top_n_per_day}")
    print(f"Skipped overlap trades: {total_skipped_overlap}")

    print("\nOVERALL")
    print("-" * 90)
    print(f"Trades:            {overall['n_trades']}")
    print(f"Win rate:          {overall['win_rate']:.1f}%")
    print(f"Avg return:        {overall['avg_return_pct']:.2f}%")
    print(f"Median return:     {overall['median_return_pct']:.2f}%")
    print(f"P&L units:         {overall['sum_units']:.4f}")
    print(f"> +10%:            {overall['pct_gt_10']:.1f}%")
    print(f"> +20%:            {overall['pct_gt_20']:.1f}%")
    print(f"< -10%:            {overall['pct_lt_minus10']:.1f}%")
    print(f"< -20%:            {overall['pct_lt_minus20']:.1f}%")

    if not trades_df.empty:
        by_chain = trades_df.groupby("chain")["forward_ret"].agg(["count", "mean", "median", "sum"])
        by_chain["win_rate"] = trades_df.groupby("chain")["forward_ret"].apply(lambda s: (s > 0).mean() * 100)
        by_chain = by_chain.sort_values("sum", ascending=False)
        print("\nBY CHAIN")
        print("-" * 90)
        print(by_chain.to_string(float_format=lambda x: f"{x:.4f}"))

    if fold_summaries:
        fold_df = pd.DataFrame(fold_summaries)
        print("\nBY FOLD")
        print("-" * 90)
        print(
            fold_df[[
                "fold", "test_start", "test_end", "train_rows", "test_rows", "candidates",
                "n_trades", "avg_return_pct", "median_return_pct", "win_rate", "sum_units",
            ]].to_string(index=False)
        )


if __name__ == "__main__":
    main()