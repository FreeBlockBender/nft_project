"""
model.py

XGBoost-based buy/sell signal classifier with:
  - Walk-forward (time-series respecting) cross-validation
  - SHAP feature importance
  - Model persistence (save / load)
  - Per-collection prediction with confidence scores
"""

import logging
import os
import pickle
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import (
    classification_report,
    precision_score,
    recall_score,
    roc_auc_score,
)

from app.ml.feature_pipeline import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Default model save path (relative to project root)
DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "ml_model.pkl"
)


# ─────────────────────────────────────────────
# Walk-forward CV splits
# ─────────────────────────────────────────────

def walk_forward_splits(
    df: pd.DataFrame,
    n_splits: int = 5,
    train_min_months: int = 6,
    test_months: int = 1,
):
    """
    Generate (train_idx, test_idx) pairs using expanding-window walk-forward splits.

    The dataset is split by date so that:
      - Training always precedes test in time (no lookahead)
      - Each fold expands the training window by `test_months`

    Parameters
    ----------
    df : pd.DataFrame  (must contain a 'date' column, already sorted)
    n_splits : int     Number of folds
    train_min_months : int  Minimum months in first training window
    test_months : int  Months per test fold

    Yields
    ------
    (train_indices, test_indices)
    """
    df = df.reset_index(drop=True)
    dates = df["date"]
    min_date = dates.min()
    max_date = dates.max()
    total_days = (max_date - min_date).days

    train_start_days = train_min_months * 30
    test_size_days = test_months * 30

    if total_days < train_start_days + test_size_days:
        logger.warning("Not enough data for walk-forward CV. Using single split.")
        cutoff = min_date + pd.Timedelta(days=int(total_days * 0.75))
        yield (
            df[dates <= cutoff].index.tolist(),
            df[dates > cutoff].index.tolist(),
        )
        return

    # Calculate fold boundaries
    available_days = total_days - train_start_days
    fold_step = max(test_size_days, available_days // n_splits)

    for i in range(n_splits):
        train_end = min_date + pd.Timedelta(days=train_start_days + i * fold_step)
        test_end = train_end + pd.Timedelta(days=fold_step)

        if test_end > max_date:
            break

        train_idx = df[dates <= train_end].index.tolist()
        test_idx = df[(dates > train_end) & (dates <= test_end)].index.tolist()

        if len(train_idx) < 100 or len(test_idx) < 10:
            continue

        yield train_idx, test_idx


# ─────────────────────────────────────────────
# Dataset preparation
# ─────────────────────────────────────────────

def prepare_dataset(
    df: pd.DataFrame,
    label_col: str = "label_binary",
    drop_na_label: bool = True,
) -> tuple[pd.DataFrame, pd.Series]:
    """
    Extract feature matrix X and label vector y from the feature dataframe.
    Drops rows with NaN labels (end-of-series rows without forward returns).

    Parameters
    ----------
    df : pd.DataFrame   Output of add_labels()
    label_col : str     'label_binary' or 'label_3class'
    drop_na_label : bool

    Returns
    -------
    (X, y) where X has only FEATURE_COLUMNS present in df
    """
    available_features = [c for c in FEATURE_COLUMNS if c in df.columns]
    if not available_features:
        raise ValueError("No feature columns found in dataframe.")

    missing_feats = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing_feats:
        logger.warning("Missing features (will be skipped): %s", missing_feats)

    X = df[available_features].copy()
    y = df[label_col].copy()

    if drop_na_label:
        mask = y.notna()
        X, y = X[mask], y[mask]

    # Replace infinities with NaN (XGBoost handles NaN natively)
    X = X.replace([np.inf, -np.inf], np.nan)

    logger.info(
        "Dataset: %d rows, %d features | label='%s' | classes: %s",
        len(X), len(available_features), label_col, dict(y.value_counts()),
    )
    return X, y


# ─────────────────────────────────────────────
# Model training
# ─────────────────────────────────────────────

def build_xgb_params(label_col: str = "label_binary") -> dict:
    """Return sensible default XGBoost hyperparameters."""
    base = dict(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_alpha=0.5,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        early_stopping_rounds=30,
        eval_metric="logloss",
    )
    if label_col == "label_binary":
        base["objective"] = "binary:logistic"
    else:
        base["objective"] = "multi:softprob"
        base["num_class"] = 3
        base["eval_metric"] = "mlogloss"
    return base


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: Optional[pd.DataFrame] = None,
    y_val: Optional[pd.Series] = None,
    label_col: str = "label_binary",
    verbose: bool = False,
) -> xgb.XGBClassifier:
    """
    Train an XGBoost classifier.

    Parameters
    ----------
    X_train, y_train : training data
    X_val, y_val     : optional validation set for early stopping
    label_col        : 'label_binary' or 'label_3class'
    verbose          : whether to print XGBoost training log

    Returns
    -------
    Fitted XGBClassifier
    """
    params = build_xgb_params(label_col)

    # For 3-class, shift labels -1→0, 0→1, 1→2 (XGBoost needs 0-based)
    y_tr = y_train.copy()
    y_v = y_val.copy() if y_val is not None else None
    if label_col == "label_3class":
        y_tr = y_tr + 1  # -1→0, 0→1, 1→2
        if y_v is not None:
            y_v = y_v + 1

    # Compute sample weights for class imbalance
    class_counts = y_tr.value_counts()
    total = len(y_tr)
    sample_weights = y_tr.map(
        {cls: total / (len(class_counts) * cnt) for cls, cnt in class_counts.items()}
    ).fillna(1.0)

    model = xgb.XGBClassifier(**params)

    fit_kwargs = dict(
        sample_weight=sample_weights,
        verbose=verbose,
    )
    if X_val is not None and y_v is not None:
        fit_kwargs["eval_set"] = [(X_val, y_v)]

    model.fit(X_train, y_tr, **fit_kwargs)
    return model


# ─────────────────────────────────────────────
# Walk-forward cross-validation
# ─────────────────────────────────────────────

def walk_forward_cv(
    df: pd.DataFrame,
    label_col: str = "label_binary",
    n_splits: int = 5,
) -> dict:
    """
    Run walk-forward cross-validation and report performance per fold.

    Returns
    -------
    dict with keys: 'fold_results', 'mean_precision', 'mean_recall', 'mean_auc'
    """
    df_sorted = df.sort_values("date").reset_index(drop=True)
    X_all, y_all = prepare_dataset(df_sorted, label_col=label_col)

    fold_results = []
    splits = list(walk_forward_splits(df_sorted, n_splits=n_splits))

    logger.info("Running %d-fold walk-forward CV ...", len(splits))

    for i, (train_idx, test_idx) in enumerate(splits):
        # Intersect with valid (non-NaN label) indices
        valid_idx = set(X_all.index)
        tr = [ix for ix in train_idx if ix in valid_idx]
        te = [ix for ix in test_idx if ix in valid_idx]

        if len(tr) < 50 or len(te) < 10:
            logger.warning("Fold %d: insufficient data, skipping.", i + 1)
            continue

        X_tr, y_tr = X_all.loc[tr], y_all.loc[tr]
        X_te, y_te = X_all.loc[te], y_all.loc[te]

        # Use last 20% of training as val for early stopping
        val_cut = int(len(tr) * 0.8)
        X_v, y_v = X_tr.iloc[val_cut:], y_tr.iloc[val_cut:]
        X_tr2, y_tr2 = X_tr.iloc[:val_cut], y_tr.iloc[:val_cut]

        model = train_model(X_tr2, y_tr2, X_val=X_v, y_val=y_v, label_col=label_col)

        # Adjust back for 3-class
        y_pred_raw = model.predict(X_te)
        if label_col == "label_3class":
            y_pred = pd.Series(y_pred_raw - 1, index=y_te.index)
        else:
            y_pred = pd.Series(y_pred_raw, index=y_te.index)

        y_prob = model.predict_proba(X_te)

        prec = precision_score(y_te, y_pred, average="weighted", zero_division=0)
        rec = recall_score(y_te, y_pred, average="weighted", zero_division=0)

        try:
            if label_col == "label_binary":
                auc = roc_auc_score(y_te, y_prob[:, 1])
            else:
                auc = roc_auc_score(y_te + 1, y_prob, multi_class="ovr")
        except Exception:
            auc = np.nan

        train_start = df_sorted["date"].iloc[min(tr)]
        train_end = df_sorted["date"].iloc[max(tr)]
        test_start = df_sorted["date"].iloc[min(te)]
        test_end = df_sorted["date"].iloc[max(te)]

        logger.info(
            "Fold %d | Train %s→%s | Test %s→%s | Prec=%.3f Rec=%.3f AUC=%.3f",
            i + 1,
            train_start.date(), train_end.date(),
            test_start.date(), test_end.date(),
            prec, rec, auc,
        )
        fold_results.append({
            "fold": i + 1,
            "train_start": train_start, "train_end": train_end,
            "test_start": test_start, "test_end": test_end,
            "precision": prec, "recall": rec, "auc": auc,
            "n_train": len(tr), "n_test": len(te),
        })

    if not fold_results:
        logger.error("No valid folds produced.")
        return {}

    fp = pd.DataFrame(fold_results)
    result = {
        "fold_results": fp,
        "mean_precision": fp["precision"].mean(),
        "mean_recall": fp["recall"].mean(),
        "mean_auc": fp["auc"].mean(),
    }
    logger.info(
        "CV summary: mean Precision=%.3f | Recall=%.3f | AUC=%.3f",
        result["mean_precision"], result["mean_recall"], result["mean_auc"],
    )
    return result


# ─────────────────────────────────────────────
# Final model + SHAP
# ─────────────────────────────────────────────

def train_final_model(
    df: pd.DataFrame,
    label_col: str = "label_binary",
    train_cutoff_date: Optional[str] = None,
) -> tuple[xgb.XGBClassifier, list[str]]:
    """
    Train on all data up to train_cutoff_date (default: all available data).

    Returns
    -------
    (model, feature_names)
    """
    if train_cutoff_date:
        df_train = df[df["date"] <= pd.to_datetime(train_cutoff_date)]
    else:
        df_train = df

    df_train = df_train.sort_values("date").reset_index(drop=True)
    X, y = prepare_dataset(df_train, label_col=label_col)
    feature_names = X.columns.tolist()

    # Hold out last 10% for early stopping
    val_cut = int(len(X) * 0.90)
    X_tr, y_tr = X.iloc[:val_cut], y.iloc[:val_cut]
    X_v, y_v = X.iloc[val_cut:], y.iloc[val_cut:]

    logger.info("Training final model on %d rows ...", len(X_tr))
    model = train_model(X_tr, y_tr, X_val=X_v, y_val=y_v, label_col=label_col)
    logger.info("Final model trained. Best iteration: %d", model.best_iteration)

    return model, feature_names


def compute_shap_importance(
    model: xgb.XGBClassifier,
    X_sample: pd.DataFrame,
    top_n: int = 15,
) -> pd.DataFrame:
    """
    Compute SHAP feature importance on a sample of data.

    Returns DataFrame with columns ['feature', 'mean_abs_shap'] sorted descending.
    """
    logger.info("Computing SHAP values on %d samples ...", len(X_sample))
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

    if isinstance(shap_values, list):
        # Multi-class: average absolute SHAP across classes
        abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        abs_shap = np.abs(shap_values)

    importance = pd.DataFrame({
        "feature": X_sample.columns,
        "mean_abs_shap": abs_shap.mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=False).head(top_n).reset_index(drop=True)

    return importance


# ─────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────

def predict_signals(
    model: xgb.XGBClassifier,
    df: pd.DataFrame,
    label_col: str = "label_binary",
    as_of_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Generate buy/sell signals for the most recent available date per collection.

    Parameters
    ----------
    model        : trained XGBClassifier
    df           : feature dataframe (output of build_feature_dataframe, NO labels needed)
    label_col    : 'label_binary' or 'label_3class'
    as_of_date   : date string 'YYYY-MM-DD'; defaults to latest date in df

    Returns
    -------
    DataFrame with columns:
        collection_identifier, slug, chain, date,
        floor_native, floor_usd,
        signal, confidence, top_features (SHAP-based, if available)
    """
    available_features = [c for c in FEATURE_COLUMNS if c in df.columns]

    if as_of_date:
        target_date = pd.to_datetime(as_of_date)
    else:
        target_date = df["date"].max()

    # Get the latest row per collection on or before target_date
    df_pred = (
        df[df["date"] <= target_date]
        .sort_values("date")
        .groupby(["collection_identifier", "chain"])
        .last()
        .reset_index()
    )

    if df_pred.empty:
        logger.warning("No rows available for prediction as of %s", target_date)
        return pd.DataFrame()

    X_pred = df_pred[available_features].replace([np.inf, -np.inf], np.nan)

    proba = model.predict_proba(X_pred)
    pred_raw = model.predict(X_pred)

    if label_col == "label_3class":
        pred = pred_raw - 1  # shift back: 0→-1, 1→0, 2→1
        signal_map = {1: "BUY", 0: "HOLD", -1: "SELL"}
        # Confidence = probability of predicted class
        confidence = proba[np.arange(len(pred_raw)), pred_raw]
    else:
        pred = pred_raw
        signal_map = {1: "BUY", 0: "HOLD"}
        confidence = proba[:, 1]  # P(BUY)

    df_pred["signal"] = pd.Series(pred, index=df_pred.index).map(signal_map)
    df_pred["confidence"] = confidence

    # SHAP top features per row (computationally expensive, skip for large batches)
    df_pred["top_features"] = None
    if len(df_pred) <= 200:
        try:
            explainer = shap.TreeExplainer(model)
            sv = explainer.shap_values(X_pred)
            if isinstance(sv, list):
                sv = np.mean([np.abs(s) for s in sv], axis=0)
            feat_names = available_features
            for idx in range(len(df_pred)):
                top3 = np.argsort(np.abs(sv[idx]))[::-1][:3]
                df_pred.at[df_pred.index[idx], "top_features"] = ", ".join(
                    f"{feat_names[j]}={sv[idx][j]:+.3f}" for j in top3
                )
        except Exception as e:
            logger.warning("SHAP per-row failed: %s", e)

    cols = [
        "collection_identifier", "slug", "chain", "date",
        "floor_native", "floor_usd",
        "signal", "confidence", "top_features",
    ]
    cols = [c for c in cols if c in df_pred.columns]
    result = df_pred[cols].sort_values("confidence", ascending=False).reset_index(drop=True)
    return result


# ─────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────

def save_model(model: xgb.XGBClassifier, feature_names: list[str], path: str = DEFAULT_MODEL_PATH):
    """Serialize model + feature names to disk."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    payload = {
        "model": model,
        "feature_names": feature_names,
        "trained_at": datetime.utcnow().isoformat(),
    }
    with open(path, "wb") as f:
        pickle.dump(payload, f)
    logger.info("Model saved to %s", path)


def load_model(path: str = DEFAULT_MODEL_PATH) -> tuple[xgb.XGBClassifier, list[str]]:
    """Load model and feature names from disk."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model file not found: {path}")
    with open(path, "rb") as f:
        payload = pickle.load(f)
    logger.info(
        "Model loaded from %s (trained at %s)",
        path, payload.get("trained_at", "unknown"),
    )
    return payload["model"], payload["feature_names"]
