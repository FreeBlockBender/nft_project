"""
feature_pipeline.py

Builds the ML feature dataframe from SQLite tables:
  - historical_nft_data   → price, volume, listing features
  - nft_social_hype       → market-wide hype score (daily)
  - nft_x_sentiment       → per-collection X/Twitter sentiment (monthly, forward-filled)
  - fear_greed_daily      → market-wide crypto Fear & Greed index (daily)
  - crypto_daily_metrics  → chain-native currency price/volume momentum + BTC macro

Returns one row per (collection_identifier, slug, chain, date) with all engineered features.
No lookahead: every feature at date t is computed using only data up to and including t.
"""

import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Chain encoding
# ─────────────────────────────────────────────
CHAIN_MAP = {
    "ethereum": 0,
    "solana": 1,
    "polygon": 2,
    "base": 3,
    "avalanche": 4,
    "arbitrum": 5,
    "optimism": 6,
    "bnb": 7,
    "blast": 8,
}

# Chain → native crypto symbol (must match crypto_symbol values in crypto_daily_metrics)
CHAIN_TO_NATIVE = {
    "ethereum": "ETH",
    "base": "ETH",      # Base L2 settles in ETH
    "polygon": "MATIC",
    "solana": "SOL",
    "arbitrum": "ARB",
    "optimism": "OP",
    "bnb": "BNB",
    "blast": "BLAST",
    # avalanche → AVAX not in DB yet, will produce NaN (handled gracefully)
}

# Symbols (other than CHAIN_TO_NATIVE values) used as macro indicators
MACRO_SYMBOLS = ["BTC"]


def _encode_chain(chain: str) -> int:
    return CHAIN_MAP.get(str(chain).lower(), 99)


# ─────────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────────

def _load_price_data(conn: sqlite3.Connection, since_date: str = None) -> pd.DataFrame:
    """
    Load raw price rows, sorted by collection + date.

    Parameters
    ----------
    since_date : str or None
        If provided (format 'YYYY-MM-DD'), only loads rows on or after this date.
        Used in prediction-only (low-RAM) mode to avoid loading full history.
        Minimum recommended window: 280 calendar days (covers MA200 + buffer).
    """
    date_filter = f"AND h.latest_floor_date >= '{since_date}'" if since_date else ""
    df = pd.read_sql_query(
        f"""
        -- For each unique slug, keep only the (collection_identifier, chain) pair
        -- with the most historical rows.  This deduplicates collections that were
        -- re-ingested under a different collection_identifier (same slug = same NFT
        -- project), halving the apparent collection count from ~2800 to ~1400.
        WITH counts AS (
            SELECT
                slug,
                collection_identifier,
                chain,
                COUNT(*) AS cnt
            FROM historical_nft_data
            GROUP BY slug, collection_identifier, chain
        ),
        canonical AS (
            SELECT
                slug,
                collection_identifier,
                chain
            FROM (
                SELECT
                    slug,
                    collection_identifier,
                    chain,
                    ROW_NUMBER() OVER (
                        PARTITION BY slug
                        ORDER BY cnt DESC, collection_identifier ASC
                    ) AS rn
                FROM counts
            )
            WHERE rn = 1
        )
        SELECT
            h.collection_identifier,
            h.slug,
            h.chain,
            h.latest_floor_date           AS date,
            h.floor_native,
            h.floor_usd,
            h.sale_count_24h,
            h.sale_volume_native_24h,
            h.highest_sale_native_24h,
            h.lowest_sale_native_24h,
            h.listed_count,
            h.unique_owners,
            h.total_supply,
            h.ranking
        FROM historical_nft_data h
        INNER JOIN canonical c
            ON  c.collection_identifier = h.collection_identifier
            AND c.chain                 = h.chain
        WHERE 1=1 {date_filter}
        ORDER BY h.collection_identifier, h.chain, h.latest_floor_date ASC
        """,
        conn,
    )
    df["date"] = pd.to_datetime(df["date"])
    df["floor_native"] = pd.to_numeric(df["floor_native"], errors="coerce")
    df["floor_usd"] = pd.to_numeric(df["floor_usd"], errors="coerce")
    return df


def _load_social_hype(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load market-wide daily hype signals."""
    df = pd.read_sql_query(
        "SELECT date, hype_score, sentiment, trend FROM nft_social_hype ORDER BY date ASC",
        conn,
    )
    df["date"] = pd.to_datetime(df["date"])

    # Encode categorical columns
    sentiment_map = {"POSITIVE": 1, "NEUTRAL": 0, "NEGATIVE": -1}
    trend_map = {"UP": 1, "STABLE": 0, "DOWN": -1}
    df["hype_sentiment"] = df["sentiment"].map(sentiment_map).fillna(0).astype(int)
    df["hype_trend"] = df["trend"].map(trend_map).fillna(0).astype(int)
    df = df[["date", "hype_score", "hype_sentiment", "hype_trend"]]
    return df


def _load_x_sentiment(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load per-collection monthly X sentiment scores."""
    df = pd.read_sql_query(
        """
        SELECT
            collection_identifier,
            chain,
            date,
            sentiment_score,
            community_engagement,
            volume_activity
        FROM nft_x_sentiment
        ORDER BY collection_identifier, chain, date ASC
        """,
        conn,
    )
    df["date"] = pd.to_datetime(df["date"])
    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"], errors="coerce")
    df["community_engagement"] = pd.to_numeric(df["community_engagement"], errors="coerce")
    df["volume_activity"] = pd.to_numeric(df["volume_activity"], errors="coerce")
    return df


def _load_fear_greed(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load daily Fear & Greed index.
    Values: 0=Extreme Fear … 100=Extreme Greed.
    Dates in DB may contain a time component — normalised to date-only here.
    """
    try:
        df = pd.read_sql_query(
            "SELECT date, value FROM fear_greed_daily ORDER BY date ASC",
            conn,
        )
    except Exception:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["fear_greed_value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    # 7-day rolling change: positive = sentiment improving, negative = worsening
    df["fear_greed_change_7d"] = df["fear_greed_value"].diff(7)
    return df[["date", "fear_greed_value", "fear_greed_change_7d"]]


def _load_crypto_metrics(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Load daily crypto market data and compute rolling features per symbol.
    Returns a *wide* DataFrame (one row per date) with columns:
        {symbol}_ret_1d, {symbol}_ret_7d, {symbol}_ret_30d,
        {symbol}_vol_7d, {symbol}_ath_pct, {symbol}_volume_rel
    for every chain-native symbol + BTC as macro indicator.
    Dates in DB may contain timestamps — normalised to date-only.
    """
    try:
        df = pd.read_sql_query(
            """
            SELECT date, crypto_symbol, current_price, total_volume,
                   market_cap, ath_change_percentage
            FROM crypto_daily_metrics
            ORDER BY date ASC, crypto_symbol ASC
            """,
            conn,
        )
    except Exception:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for col in ["current_price", "total_volume", "market_cap", "ath_change_percentage"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    symbols_needed = set(CHAIN_TO_NATIVE.values()) | set(MACRO_SYMBOLS)
    available = set(df["crypto_symbol"].unique())
    symbols_to_process = symbols_needed & available

    wide_parts = []
    for sym in symbols_to_process:
        s = (
            df[df["crypto_symbol"] == sym]
            .drop_duplicates("date")
            .set_index("date")
            .sort_index()
        )
        # Expand to full daily index and forward-fill small gaps
        full_idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
        s = s.reindex(full_idx)
        p = s["current_price"].ffill(limit=3)
        log_ret = np.log(p / p.shift(1))
        prefix = sym.lower()
        part = pd.DataFrame(index=s.index)
        part[f"{prefix}_ret_1d"]     = p.pct_change(1)
        part[f"{prefix}_ret_7d"]     = p.pct_change(7)
        part[f"{prefix}_ret_30d"]    = p.pct_change(30)
        part[f"{prefix}_vol_7d"]     = log_ret.rolling(7, min_periods=3).std()
        part[f"{prefix}_ath_pct"]    = s["ath_change_percentage"].ffill(limit=3)
        # Relative volume: how much of market cap is traded daily (activity intensity)
        part[f"{prefix}_volume_rel"] = (
            s["total_volume"] / s["market_cap"].replace(0, np.nan)
        ).ffill(limit=3)
        wide_parts.append(part)

    if not wide_parts:
        return pd.DataFrame()

    wide = (
        pd.concat(wide_parts, axis=1)
        .reset_index()
        .rename(columns={"index": "date"})
    )
    return wide


# ─────────────────────────────────────────────
# Per-collection feature engineering
# ─────────────────────────────────────────────

def _compute_collection_features(grp: pd.DataFrame, max_fill_gap: int = 7) -> pd.DataFrame:
    """
    Takes a single-collection group (sorted by date) and computes all features.
    Missing price dates are forward-filled up to max_fill_gap consecutive days.
    """
    # Deduplicate: if same (collection, chain, date) appears more than once in the DB
    # (can happen due to SQLite NULL primary key edge cases), keep the row with the
    # highest floor_native. Using groupby→first after sorting guarantees a unique date index.
    grp = (
        grp.sort_values("floor_native", ascending=False)
           .groupby("date", sort=True)
           .first()
           .reset_index()
    )

    # Create a complete daily date index
    full_idx = pd.date_range(grp["date"].min(), grp["date"].max(), freq="D")
    grp = grp.set_index("date").reindex(full_idx)
    grp.index.name = "date"

    # Carry forward metadata (non-price)
    for col in ["collection_identifier", "slug", "chain"]:
        grp[col] = grp[col].ffill()

    # Forward-fill price with gap limit
    grp["floor_native"] = (
        grp["floor_native"]
        .ffill(limit=max_fill_gap)
    )
    grp["floor_usd"] = (
        grp["floor_usd"]
        .ffill(limit=max_fill_gap)
    )

    # Drop rows still missing floor_native (gaps > max_fill_gap or start of series)
    grp = grp.dropna(subset=["floor_native"])
    if grp.empty:
        return pd.DataFrame()

    p = grp["floor_native"]

    # ── Returns ──────────────────────────────────────────────────
    for n in [3, 7, 14, 30]:
        grp[f"ret_{n}d"] = p.pct_change(periods=n)

    # ── Log returns (for volatility) ────────────────────────────
    log_ret = np.log(p / p.shift(1))

    # ── Volatility: rolling std of log returns ──────────────────
    for n in [7, 14, 30]:
        grp[f"vol_{n}d"] = log_ret.rolling(n, min_periods=max(3, n // 3)).std()

    # ── Moving averages ──────────────────────────────────────────
    for ma in [20, 50, 200]:
        col = f"ma{ma}"
        grp[col] = p.rolling(ma, min_periods=ma // 2).mean()

    # ── MA ratios: floor / MA (>1 means price above MA) ─────────
    for ma in [20, 50, 200]:
        grp[f"floor_vs_ma{ma}"] = p / grp[f"ma{ma}"]

    # ── MA spreads ───────────────────────────────────────────────
    # Positive spread = short MA above long MA (bullish)
    grp["spread_20_50"] = (grp["ma20"] - grp["ma50"]) / grp["ma50"]
    grp["spread_50_200"] = (grp["ma50"] - grp["ma200"]) / grp["ma200"]

    # ── MA slope (momentum of MA itself) ────────────────────────
    for ma in [20, 50]:
        grp[f"ma{ma}_slope"] = grp[f"ma{ma}"].pct_change(5)

    # ── Listing pressure ────────────────────────────────────────
    grp["listed_count"] = grp["listed_count"].ffill(limit=7)
    grp["total_supply"] = grp["total_supply"].ffill(limit=30)
    grp["listing_ratio"] = grp["listed_count"] / grp["total_supply"].replace(0, np.nan)

    # ── Unique owner ratio ───────────────────────────────────────
    grp["unique_owners"] = grp["unique_owners"].ffill(limit=30)
    grp["owner_ratio"] = grp["unique_owners"] / grp["total_supply"].replace(0, np.nan)

    # ── Sales features (heavily sparse — fill with 0 when truly no sales) ──
    grp["sale_count_24h"] = grp["sale_count_24h"].fillna(0)
    grp["sale_volume_native_24h"] = grp["sale_volume_native_24h"].fillna(0)
    grp["sale_count_ma7"] = grp["sale_count_24h"].rolling(7, min_periods=1).mean()
    grp["sale_vol_ma7"] = grp["sale_volume_native_24h"].rolling(7, min_periods=1).mean()
    grp["sale_count_momentum"] = grp["sale_count_ma7"] / (
        grp["sale_count_24h"].rolling(30, min_periods=3).mean().replace(0, np.nan)
    )

    # ── Intraday range (when available) ─────────────────────────
    high = grp["highest_sale_native_24h"].where(grp["highest_sale_native_24h"] > 0)
    low = grp["lowest_sale_native_24h"].where(grp["lowest_sale_native_24h"] > 0)
    grp["intraday_range"] = (high - low) / p.replace(0, np.nan)

    # ── Ranking (lower is better) ────────────────────────────────
    grp["ranking"] = grp["ranking"].ffill(limit=7)

    # ── Chain encoding ───────────────────────────────────────────
    grp["chain_enc"] = _encode_chain(grp["chain"].iloc[0] if not grp["chain"].empty else "")

    grp = grp.reset_index()
    return grp


def _merge_market_features(df: pd.DataFrame, hype_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join market-wide hype signals onto the feature dataframe."""
    if hype_df.empty:
        df["hype_score"] = np.nan
        df["hype_sentiment"] = 0
        df["hype_trend"] = 0
        return df
    df = df.merge(hype_df, on="date", how="left")
    # Forward-fill hype for days without an entry (up to 7 days)
    df = df.sort_values("date")
    for col in ["hype_score", "hype_sentiment", "hype_trend"]:
        df[col] = df[col].ffill(limit=7)
    return df


def _merge_x_sentiment(df: pd.DataFrame, xsent_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join per-collection X sentiment.
    Since sentiment is updated monthly, forward-fill to cover daily rows.
    """
    if xsent_df.empty:
        df["xsent_score"] = np.nan
        df["xsent_engagement"] = np.nan
        df["xsent_volume"] = np.nan
        return df

    xsent_df = xsent_df.rename(columns={
        "sentiment_score": "xsent_score",
        "community_engagement": "xsent_engagement",
        "volume_activity": "xsent_volume",
    })

    # Merge on collection_identifier + chain + date, then forward-fill within each group
    merged = df.merge(
        xsent_df[["collection_identifier", "chain", "date", "xsent_score", "xsent_engagement", "xsent_volume"]],
        on=["collection_identifier", "chain", "date"],
        how="left",
    )

    merged = merged.sort_values(["collection_identifier", "chain", "date"])
    for col in ["xsent_score", "xsent_engagement", "xsent_volume"]:
        merged[col] = merged.groupby(["collection_identifier", "chain"])[col].transform(
            lambda s: s.ffill(limit=45)  # forward-fill up to ~45 days (monthly cadence)
        )

    return merged


def _merge_x_sentiment_asof(df: pd.DataFrame, xsent_df: pd.DataFrame) -> pd.DataFrame:
    """
    As-of x_sentiment merge for predict-only mode (df has 1 row per collection).

    For each (collection_identifier, chain) row in df, picks the most recent
    x_sentiment entry whose date is <= the row's price date.  No ffill needed
    because we directly select the latest available value.
    """
    xcols = ["xsent_score", "xsent_engagement", "xsent_volume"]
    if xsent_df.empty:
        for col in xcols:
            df[col] = np.nan
        return df

    xsent_renamed = xsent_df.rename(columns={
        "sentiment_score":       "xsent_score",
        "community_engagement":  "xsent_engagement",
        "volume_activity":       "xsent_volume",
    })

    # For every (collection_identifier, chain) get the row with the latest date
    # up to the max price date in df (safe since df already holds only the
    # "today" row per collection).
    ref_date = df["date"].max()
    latest = (
        xsent_renamed[xsent_renamed["date"] <= ref_date]
        .sort_values("date")
        .groupby(["collection_identifier", "chain"])
        .last()
        .reset_index()
    )

    merged = df.merge(
        latest[["collection_identifier", "chain"] + xcols],
        on=["collection_identifier", "chain"],
        how="left",
    )
    return merged


def _merge_fear_greed(df: pd.DataFrame, fg_df: pd.DataFrame) -> pd.DataFrame:
    """Left-join Fear & Greed features; forward-fill gaps up to 7 days."""
    if fg_df.empty:
        df["fear_greed_value"] = np.nan
        df["fear_greed_change_7d"] = np.nan
        return df
    df = df.merge(fg_df, on="date", how="left")
    df = df.sort_values("date")
    for col in ["fear_greed_value", "fear_greed_change_7d"]:
        df[col] = df[col].ffill(limit=7)
    return df


def _merge_crypto_features(df: pd.DataFrame, crypto_df: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join crypto market features onto the feature dataframe.

    Chain-native symbol columns (e.g. eth_ret_7d for 'ethereum' chains) are
    copied to neutral 'native_*' columns so the model sees one consistent
    feature name regardless of which chain a collection lives on.

    BTC columns are kept as-is (universal macro indicator).
    All symbol-specific wide columns are dropped afterwards.
    """
    native_suffixes = ["ret_1d", "ret_7d", "ret_30d", "vol_7d", "ath_pct", "volume_rel"]
    native_targets  = [f"native_{s}" for s in native_suffixes]
    btc_features    = {"btc_ret_7d": "btc_ret_7d",
                       "btc_vol_7d": "btc_vol_7d",
                       "btc_ath_pct": "btc_ath_pct"}

    if crypto_df.empty:
        for col in native_targets + list(btc_features.values()):
            df[col] = np.nan
        return df

    df = df.merge(crypto_df, on="date", how="left")

    # Initialise native_* columns
    for col in native_targets:
        df[col] = np.nan

    # Map each (chain → native symbol) → fill generic native_* columns
    chain_col = df["chain"].str.lower()
    for chain, sym in CHAIN_TO_NATIVE.items():
        prefix = sym.lower()
        mask = chain_col == chain
        if not mask.any():
            continue
        for suffix, native_col in zip(native_suffixes, native_targets):
            src = f"{prefix}_{suffix}"
            if src in df.columns:
                df.loc[mask, native_col] = df.loc[mask, src]

    # BTC macro — same value for every chain
    for src, dst in btc_features.items():
        df[dst] = df[src] if src in df.columns else np.nan

    # Drop the per-symbol wide columns (noise for the model)
    all_native_syms = set(CHAIN_TO_NATIVE.values()) | set(MACRO_SYMBOLS)
    keep = set(native_targets) | set(btc_features.values())
    drop_cols = [
        c for c in df.columns
        if any(c.startswith(s.lower() + "_") for s in all_native_syms)
        and c not in keep
    ]
    df = df.drop(columns=drop_cols, errors="ignore")

    return df


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────

FEATURE_COLUMNS = [
    # Returns
    "ret_3d", "ret_7d", "ret_14d", "ret_30d",
    # Volatility
    "vol_7d", "vol_14d", "vol_30d",
    # MA ratios
    "floor_vs_ma20", "floor_vs_ma50", "floor_vs_ma200",
    # MA spreads / slopes
    "spread_20_50", "spread_50_200", "ma20_slope", "ma50_slope",
    # Listing / ownership
    "listing_ratio", "owner_ratio",
    # Sales
    "sale_count_ma7", "sale_vol_ma7", "sale_count_momentum",
    # Intraday
    "intraday_range",
    # Ranking
    "ranking",
    # Market sentiment (nft_social_hype)
    "hype_score", "hype_sentiment", "hype_trend",
    # X/Twitter sentiment (nft_x_sentiment)
    "xsent_score", "xsent_engagement", "xsent_volume",
    # Fear & Greed index (fear_greed_daily)
    "fear_greed_value", "fear_greed_change_7d",
    # Chain-native crypto momentum (crypto_daily_metrics, mapped by chain)
    "native_ret_1d", "native_ret_7d", "native_ret_30d",
    "native_vol_7d", "native_ath_pct", "native_volume_rel",
    # BTC macro indicator (crypto_daily_metrics, universal)
    "btc_ret_7d", "btc_vol_7d", "btc_ath_pct",
    # Meta
    "chain_enc",
]


def build_feature_dataframe(
    conn: sqlite3.Connection,
    min_days: int = 60,
    max_fill_gap: int = 7,
    lookback_days: int = None,
) -> pd.DataFrame:
    """
    Build the complete ML feature dataframe.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    min_days : int
        Minimum number of observed price rows required to include a collection.
        When using lookback_days, set this low (e.g. 20) so recently-listed
        collections are not excluded.
    max_fill_gap : int
        Max consecutive missing days to forward-fill in price data.
    lookback_days : int or None
        **Prediction-only / low-RAM mode.**
        When set, only loads price data from the last `lookback_days` calendar
        days.  This reduces the price dataset from ~940K rows to ~300K rows and
        cuts peak RAM from ~1.8 GB to ~250 MB — safe for servers with <1 GB RAM.
        Minimum safe value: 280 (covers the 200-day MA + gap-fill buffer).
        Leave as None for full historical load (required for training).

    Returns
    -------
    pd.DataFrame
        Columns: collection_identifier, slug, chain, date, floor_native, floor_usd,
                 + all FEATURE_COLUMNS.
        Sorted by collection_identifier, chain, date.
    """
    since_date = None
    if lookback_days is not None:
        cur = conn.cursor()
        cur.execute("SELECT MAX(latest_floor_date) FROM historical_nft_data")
        max_db_date = pd.to_datetime(cur.fetchone()[0])
        since_date = (max_db_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        logger.info(
            "Prediction-only mode: loading price data from %s onwards (%d-day window)",
            since_date, lookback_days,
        )

    logger.info("Loading price data from DB ...")
    price_df = _load_price_data(conn, since_date=since_date)

    # Filter to collections with enough data
    counts = price_df.groupby(["collection_identifier", "chain"]).size()
    valid = counts[counts >= min_days].index
    price_df = price_df.set_index(["collection_identifier", "chain"]).loc[
        price_df.set_index(["collection_identifier", "chain"]).index.isin(valid)
    ].reset_index()
    logger.info(
        "Kept %d collections with >= %d days (total rows: %d)",
        len(valid), min_days, len(price_df),
    )

    logger.info("Loading hype, sentiment, fear/greed and crypto market data ...")
    hype_df    = _load_social_hype(conn)
    xsent_df   = _load_x_sentiment(conn)
    fg_df      = _load_fear_greed(conn)
    crypto_df  = _load_crypto_metrics(conn)
    logger.info(
        "Auxiliary data: hype=%d rows | x_sentiment=%d rows | fear_greed=%d rows | crypto_wide=%d rows",
        len(hype_df), len(xsent_df), len(fg_df), len(crypto_df),
    )

    logger.info("Engineering features per collection ...")
    groups = price_df.groupby(["collection_identifier", "chain"], sort=False)
    results = []
    skipped = 0
    for (cid, chain), grp in groups:
        feat = _compute_collection_features(grp.copy(), max_fill_gap=max_fill_gap)
        if feat.empty:
            skipped += 1
            continue
        # ── Predict-only RAM optimisation (inner loop) ───────────
        # Keep only the last date row immediately so the `results` list
        # accumulates O(N_collections) rows instead of O(280 × N_collections).
        # Rolling features have already been computed over the full window;
        # subsequent market-feature merges only need the final row.
        if lookback_days is not None:
            feat = feat.iloc[[-1]]
        results.append(feat)

    if not results:
        logger.warning("No feature data produced.")
        return pd.DataFrame()

    logger.info("Concatenating %d collections (skipped: %d) ...", len(results), skipped)
    df = pd.concat(results, ignore_index=True)

    if lookback_days is not None:
        logger.info(
            "Predict-only mode: %d rows (1 per collection) — merging market features ...",
            len(df),
        )

    logger.info("Merging market-wide hype features ...")
    df = _merge_market_features(df, hype_df)

    logger.info("Merging X sentiment features ...")
    if lookback_days is not None:
        # In predict-only mode df has 1 row per collection.
        # The normal _merge_x_sentiment relies on groupby-transform ffill across
        # many rows per collection — a no-op on single-row groups (all NaN).
        # Use an as-of lookup instead: latest sentiment entry per collection
        # with date <= today's price date.
        df = _merge_x_sentiment_asof(df, xsent_df)
    else:
        df = _merge_x_sentiment(df, xsent_df)

    logger.info("Merging Fear & Greed features ...")
    df = _merge_fear_greed(df, fg_df)

    logger.info("Merging crypto market features ...")
    df = _merge_crypto_features(df, crypto_df)

    # Final sort
    df = df.sort_values(["collection_identifier", "chain", "date"]).reset_index(drop=True)

    logger.info(
        "Feature dataframe built: %d rows, %d collections",
        len(df), df["collection_identifier"].nunique(),
    )
    return df
