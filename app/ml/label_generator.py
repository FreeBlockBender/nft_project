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

    def _calc_forward_return(grp: pd.DataFrame) -> pd.Series:
        """
        For each row in a single-collection group, look up the floor_native
        exactly `horizon_days` calendar days later using the date index.
        Uses date-based lookup (not integer shift) so gaps in the series
        are handled correctly — we look for the closest available date
        within horizon ± 2 days.
        """
        grp = grp.set_index("date")["floor_native"]
        fwd_ret = pd.Series(np.nan, index=grp.index, name="forward_ret")

        for dt in grp.index:
            target_dt = dt + pd.Timedelta(days=horizon_days)
            # Allow ±2 day tolerance for missing trading days
            for offset in [0, 1, -1, 2, -2]:
                candidate = target_dt + pd.Timedelta(days=offset)
                if candidate in grp.index and pd.notna(grp[candidate]) and grp[dt] > 0:
                    fwd_ret[dt] = (grp[candidate] - grp[dt]) / grp[dt]
                    break

        return fwd_ret.values  # return as array, aligned to grp's order

    logger.info(
        "Computing forward returns (horizon=%dd, buy>=%.0f%%, sell<=-%.0f%%) ...",
        horizon_days, buy_threshold * 100, sell_threshold * 100,
    )

    fwd_rets = (
        df.groupby(["collection_identifier", "chain"], sort=False)
        .apply(_calc_forward_return)
    )

    # Flatten multi-index result back onto df
    flat_fwd = []
    for (cid, chain), arr in fwd_rets.items():
        mask = (df["collection_identifier"] == cid) & (df["chain"] == chain)
        flat_fwd.append(pd.Series(arr, index=df[mask].index))

    df["forward_ret"] = pd.concat(flat_fwd).sort_index()

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
