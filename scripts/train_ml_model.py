"""
train_ml_model.py

End-to-end training pipeline for the NFT buy/sell signal model.

Usage:
    python scripts/train_ml_model.py [--horizon 14] [--threshold 0.10] [--min-days 60]
                                     [--label binary|3class] [--no-cv] [--model-path PATH]

Steps:
    1. Build feature dataframe from DB
    2. Generate forward-return labels
    3. Walk-forward cross-validation (reports precision / recall / AUC per fold)
    4. Train final model on all data
    5. Print SHAP feature importance
    6. Save model to disk
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
from app.ml.feature_pipeline import build_feature_dataframe
from app.ml.label_generator import add_labels
from app.ml.model import (
    walk_forward_cv,
    train_final_model,
    compute_shap_importance,
    prepare_dataset,
    save_model,
    DEFAULT_MODEL_PATH,
)


def parse_args():
    p = argparse.ArgumentParser(description="Train NFT buy/sell ML model")
    p.add_argument("--horizon",     type=int,   default=14,   help="Forward return horizon in days (default: 14)")
    p.add_argument("--threshold",   type=float, default=0.10, help="Return threshold for BUY/SELL label (default: 0.10 = 10%%)")
    p.add_argument("--min-days",    type=int,   default=60,   help="Min price days required per collection (default: 60)")
    p.add_argument("--label",       type=str,   default="binary", choices=["binary", "3class"],
                   help="Label type: binary (BUY/not-BUY) or 3class (BUY/HOLD/SELL)")
    p.add_argument("--no-cv",       action="store_true",     help="Skip walk-forward CV (faster)")
    p.add_argument("--cv-splits",   type=int,   default=5,   help="Number of walk-forward CV folds (default: 5)")
    p.add_argument("--model-path",  type=str,   default=DEFAULT_MODEL_PATH, help="Where to save the trained model")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()

    label_col = "label_binary" if args.label == "binary" else "label_3class"
    logging.info("=" * 60)
    logging.info("NFT ML Model Training")
    logging.info("  horizon=%d days | threshold=%.0f%% | label=%s | min_days=%d",
                 args.horizon, args.threshold * 100, label_col, args.min_days)
    logging.info("=" * 60)

    # ── 1. Feature pipeline ──────────────────────────────────────
    conn = get_db_connection()
    try:
        df = build_feature_dataframe(conn, min_days=args.min_days)
    finally:
        conn.close()

    if df.empty:
        logging.error("Feature dataframe is empty. Aborting.")
        sys.exit(1)

    logging.info("Feature dataframe: %d rows, %d collections, date range %s → %s",
                 len(df), df["collection_identifier"].nunique(),
                 df["date"].min().date(), df["date"].max().date())

    # ── 2. Label generation ──────────────────────────────────────
    df = add_labels(
        df,
        horizon_days=args.horizon,
        buy_threshold=args.threshold,
        sell_threshold=args.threshold,
    )

    labeled = df[df[label_col].notna()]
    logging.info("Labeled rows: %d (dropped %d end-of-series NaN rows)",
                 len(labeled), len(df) - len(labeled))

    if len(labeled) < 200:
        logging.error("Too few labeled rows (%d). Need at least 200. Aborting.", len(labeled))
        sys.exit(1)

    # ── 3. Walk-forward CV ───────────────────────────────────────
    if not args.no_cv:
        logging.info("Running walk-forward cross-validation ...")
        cv_results = walk_forward_cv(df, label_col=label_col, n_splits=args.cv_splits)
        if cv_results:
            logging.info("CV Results:")
            logging.info(cv_results["fold_results"].to_string(index=False))
            logging.info("Mean Precision: %.4f", cv_results["mean_precision"])
            logging.info("Mean Recall:    %.4f", cv_results["mean_recall"])
            logging.info("Mean AUC:       %.4f", cv_results["mean_auc"])
        else:
            logging.warning("CV produced no results.")
    else:
        logging.info("Walk-forward CV skipped (--no-cv).")

    # ── 4. Train final model ─────────────────────────────────────
    logging.info("Training final model on all available data ...")
    model, feature_names = train_final_model(df, label_col=label_col)

    # ── 5. SHAP feature importance ───────────────────────────────
    X_all, _ = prepare_dataset(df, label_col=label_col)
    sample_size = min(2000, len(X_all))
    X_sample = X_all.sample(sample_size, random_state=42)

    logging.info("Computing SHAP feature importance (sample=%d) ...", sample_size)
    importance = compute_shap_importance(model, X_sample, top_n=len(feature_names))

    logging.info("\nTop 15 Features by SHAP Importance:")
    logging.info("\n%s", importance.head(15).to_string(index=False))

    # ── 6. Save model ────────────────────────────────────────────
    save_model(model, feature_names, path=args.model_path)
    logging.info("Training complete. Model saved to: %s", args.model_path)


if __name__ == "__main__":
    main()
