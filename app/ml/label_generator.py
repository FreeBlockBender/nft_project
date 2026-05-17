"""
label_generator.py

Generates buy/sell/hold labels for the ML model.

Label definition:
  forward_return_N = (floor_native_{t+N} - floor_native_t) / floor_native_t

  BUY  (1):  forward_return_N >  +buy_threshold
  SELL (-1): forward_return_N <  -sell_threshold
  HOLD (0):  everything in between

Labels are computed strictly within each (collection, chain) group to avoid
cross-collection lookahead bias.
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def add_labels(
    df: pd.DataFrame,
    horizon_days: int = 14,
    buy_threshold: float = 0.10,
    sell_threshold: float = 0.10,
) -> pd.DataFrame:
    """
    Add label columns to the feature dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Output of build_feature_dataframe(). Must contain 'collection_identifier',
        'chain', 'date', 'floor_native'.
    horizon_days : int
        Number of calendar days to look forward for the return.
        Default=14 (2-week holding period).
    buy_threshold : float
        Minimum forward return to be labelled BUY. Default=0.10 (10%).
    sell_threshold : float
        Minimum forward loss to be labelled SELL. Default=0.10 (10%).

    Returns
    -------
    pd.DataFrame
        Input dataframe with three additional columns:
          - forward_ret  : raw forward return (float, NaN at end of series)
          - label_3class : -1 SELL, 0 HOLD, 1 BUY
          - label_binary : 1 BUY, 0 NOT-BUY (for simpler binary classification)
    """
    df = df.sort_values(["collection_identifier", "chain", "date"]).copy()

    logger.info(
        "Computing forward returns (horizon=%dd, buy>=%.0f%%, sell<=-%.0f%%) ...",
        horizon_days, buy_threshold * 100, sell_threshold * 100,
    )

    # ── Vectorized forward-return via self-join (replaces per-row Python loop) ──
    # Build a lookup table: (collection, chain, date) → floor_native
    lookup = (
        df[["collection_identifier", "chain", "date", "floor_native"]]
        .drop_duplicates(["collection_identifier", "chain", "date"])
        .rename(columns={"date": "_fdate", "floor_native": "_fprice"})
    )

    forward_ret = pd.Series(np.nan, index=df.index, dtype=float)

    for offset in [0, 1, -1, 2, -2]:
        still_nan_idx = forward_ret[forward_ret.isna()].index
        if len(still_nan_idx) == 0:
            break

        sub = pd.DataFrame({
            "_orig_idx": still_nan_idx,
            "collection_identifier": df.loc[still_nan_idx, "collection_identifier"].values,
            "chain":                 df.loc[still_nan_idx, "chain"].values,
            "_fdate":                (df.loc[still_nan_idx, "date"] + pd.Timedelta(days=horizon_days + offset)).values,
            "_cprice":               df.loc[still_nan_idx, "floor_native"].values,
        })

        merged = sub.merge(lookup, on=["collection_identifier", "chain", "_fdate"], how="left")
        valid = merged["_fprice"].notna().values & (merged["_cprice"].values > 0)

        orig_idx_valid = merged.loc[valid, "_orig_idx"].values
        fp = merged.loc[valid, "_fprice"].values
        cp = merged.loc[valid, "_cprice"].values
        forward_ret.loc[orig_idx_valid] = (fp - cp) / cp

    df["forward_ret"] = forward_ret

    # ── Build labels ─────────────────────────────────────────────
    def _classify(r):
        if pd.isna(r):
            return np.nan
        if r >= buy_threshold:
            return 1
        if r <= -sell_threshold:
            return -1
        return 0

    df["label_3class"] = df["forward_ret"].map(_classify)
    df["label_binary"] = (df["forward_ret"] >= buy_threshold).astype(float)
    df.loc[df["forward_ret"].isna(), "label_binary"] = np.nan

    # Stats
    valid = df["label_3class"].dropna()
    total = len(valid)
    if total > 0:
        buy_pct = (valid == 1).sum() / total * 100
        sell_pct = (valid == -1).sum() / total * 100
        hold_pct = (valid == 0).sum() / total * 100
        logger.info(
            "Label distribution (n=%d): BUY=%.1f%% | HOLD=%.1f%% | SELL=%.1f%%",
            total, buy_pct, hold_pct, sell_pct,
        )

    return df


def get_class_weights(y: pd.Series) -> dict:
    """
    Compute inverse-frequency class weights for imbalanced datasets.
    Returns a dict {class_value: weight} suitable for XGBoost's sample_weight.
    """
    counts = y.value_counts()
    total = len(y)
    weights = {cls: total / (len(counts) * cnt) for cls, cnt in counts.items()}
    return weights
