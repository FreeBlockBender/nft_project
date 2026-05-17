"""
GC Pattern Analyzer -- NFT Collections (Ranking <= MAX_RANKING)
===============================================================
Scans collections with ranking <= MAX_RANKING for active Golden Cross signals
on BOTH the 20/50 and 50/200 MA pairs, then generates a narrative report per
collection showing:
  - Per-pair: signal date, weeks in, distance from anchor MA, historical pattern
  - Cross-pair relationship: which fired first, gap, alignment status

Usage:
    python scripts/analyze_gc_patterns.py [--ranking 150] [--lookback 180] [--min-weeks 0]
    python scripts/analyze_gc_patterns.py --ranking 50 --lookback 365
"""

import sys
import os
import argparse
from datetime import datetime, timedelta, timezone

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.db_connection import get_db_connection
from app.golden_cross.moving_average import calculate_sma

# -------- Config --------
MAX_RANKING = 150
ACTIVE_GC_LOOKBACK_DAYS = 180
PEAK_LOOKFORWARD_DAYS = 365
REVERSAL_DROP = 0.20   # 20% drawdown from peak = "topped out"

MA_PAIRS = {
    "20/50":  {"short": 20, "long": 50,  "short_thresh": 1,  "long_thresh": 5},
    "50/200": {"short": 50, "long": 200, "short_thresh": 5,  "long_thresh": 20},
}

# All unique MA periods needed across both pairs
ALL_MA_PERIODS = {
    20: 1,   # period -> missing_threshold
    50: 5,
    200: 20,
}
# -------------------------


# ──────────────────────── DB helpers ────────────────────────

def get_latest_ranking(conn, slug, chain) -> int | None:
    cur = conn.cursor()
    cur.execute(
        """SELECT ranking FROM historical_nft_data
           WHERE slug = ? AND chain = ? AND ranking IS NOT NULL
           ORDER BY latest_floor_date DESC LIMIT 1""",
        (slug, chain),
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_price_series(conn, slug, chain) -> list[tuple[str, float]]:
    cur = conn.cursor()
    cur.execute(
        """SELECT latest_floor_date, floor_native
           FROM historical_nft_data
           WHERE slug = ? AND chain = ? AND floor_native IS NOT NULL
           ORDER BY latest_floor_date ASC""",
        (slug, chain),
    )
    return cur.fetchall()


def get_all_gc_events(conn, slug, chain, short_period, long_period) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """SELECT date, floor_native, ma_short, ma_long, ranking
           FROM historical_golden_crosses
           WHERE slug = ? AND chain = ?
             AND is_native = 1
             AND ma_short_period = ? AND ma_long_period = ?
           ORDER BY date ASC""",
        (slug, chain, short_period, long_period),
    )
    return [
        {"date": r[0], "floor_native": r[1], "ma_short": r[2], "ma_long": r[3], "ranking": r[4]}
        for r in cur.fetchall()
    ]


def get_recent_active_gcs_for_pair(conn, lookback_days, short_period, long_period) -> list[dict]:
    cutoff = (_now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute(
        """SELECT slug, chain, MAX(date) as latest_gc_date
           FROM historical_golden_crosses
           WHERE is_native = 1
             AND ma_short_period = ? AND ma_long_period = ?
             AND date >= ?
           GROUP BY slug, chain""",
        (short_period, long_period, cutoff),
    )
    return [{"slug": r[0], "chain": r[1], "gc_date": r[2]} for r in cur.fetchall()]


# ──────────────────────── Analysis ────────────────────────

def compute_ma(price_series, period, thresh) -> float | None:
    if not price_series or len(price_series) < period:
        return None
    val = calculate_sma(price_series, period, price_series[-1][0], thresh)
    import math
    return None if (val is None or (isinstance(val, float) and math.isnan(val))) else val


def analyze_past_gc(price_series: list, gc_date_str: str) -> dict:
    """
    For a past GC, compute forward metrics:
      peak_return_pct, weeks_to_peak, total_weeks (until 20% drawdown), outcome
    """
    gc_date = datetime.strptime(gc_date_str, "%Y-%m-%d")

    entry_price = None
    entry_date = None
    for d, v in price_series:
        if datetime.strptime(d, "%Y-%m-%d") >= gc_date:
            entry_price = v
            entry_date = datetime.strptime(d, "%Y-%m-%d")
            break

    if not entry_price:
        return {"outcome": "NO_DATA"}

    cutoff = gc_date + timedelta(days=PEAK_LOOKFORWARD_DAYS)
    forward = [
        (datetime.strptime(d, "%Y-%m-%d"), v)
        for d, v in price_series
        if gc_date <= datetime.strptime(d, "%Y-%m-%d") <= cutoff
    ]
    if not forward:
        return {"outcome": "NO_DATA"}

    peak_price, peak_date = entry_price, entry_date
    for dt, price in forward:
        if price > peak_price:
            peak_price, peak_date = price, dt

    peak_return_pct = (peak_price - entry_price) / entry_price * 100
    weeks_to_peak = (peak_date - entry_date).days / 7

    reversal_date = None
    for dt, price in forward:
        if dt <= peak_date:
            continue
        if (peak_price - price) / peak_price >= REVERSAL_DROP:
            reversal_date = dt
            break

    total_weeks = (reversal_date - entry_date).days / 7 if reversal_date else None

    outcome = "RUNNER" if peak_return_pct >= 50 else ("MODERATE" if peak_return_pct >= 15 else "FAILED")
    return {
        "entry_price": entry_price,
        "peak_price": peak_price,
        "peak_return_pct": peak_return_pct,
        "weeks_to_peak": weeks_to_peak,
        "total_weeks": total_weeks,
        "reversal_date": reversal_date.strftime("%Y-%m-%d") if reversal_date else None,
        "outcome": outcome,
    }


# ──────────────────────── Formatting ────────────────────────

def distance_label_ma50(pct: float) -> str:
    if pct < 0:
        return "BELOW MA50 - momentum signal may have failed"
    elif pct < 5:
        return "just above MA50 - very early, confirm hold"
    elif pct < 20:
        return "constructive short-term"
    elif pct < 40:
        return "extended short-term"
    else:
        return "very stretched vs MA50"


def distance_label_ma200(pct: float) -> str:
    if pct < 0:
        return "BELOW MA200 - long-term setup may be failing"
    elif pct < 15:
        return "close to MA200 - early stage"
    elif pct < 40:
        return "constructive - above MA200, not stretched"
    elif pct < 70:
        return "getting extended"
    else:
        return "very stretched vs MA200"


def format_pair_block(pair_label, cfg, current_gc, past_analyses, weeks_in,
                      current_floor, anchor_ma, chain_sym) -> list[str]:
    """Render the block for one MA pair (20/50 or 50/200)."""
    long_ = cfg["long"]
    lines = []
    lines.append(f"  [ GC {pair_label} ]  fired {current_gc['date']}  ({weeks_in:.1f} wks ago)")
    lines.append(f"    Floor at signal  : {current_gc['floor_native']:.4f} {chain_sym}")

    if current_floor and anchor_ma:
        pct = (current_floor - anchor_ma) / anchor_ma * 100
        label_fn = distance_label_ma50 if pair_label == "20/50" else distance_label_ma200
        lines.append(
            f"    Distance from MA{long_} : {pct:+.1f}%  ->  {label_fn(pct)}"
        )

    if past_analyses:
        lines.append(f"    History ({len(past_analyses)} prior event(s)):")
        for i, a in enumerate(past_analyses, 1):
            if a.get("outcome") == "NO_DATA":
                lines.append(f"      [{i}] No data")
                continue
            reversal_str = (
                f"  topped ~{a['total_weeks']:.1f} wks  ({a['reversal_date']})"
                if a.get("total_weeks") else "  no clear reversal yet"
            )
            lines.append(
                f"      [{i}]  Peak {a['peak_return_pct']:+.0f}%  "
                f"in {a['weeks_to_peak']:.1f} wks{reversal_str}  [{a['outcome']}]"
            )

        valid = [a for a in past_analyses if a.get("outcome") != "NO_DATA"]
        if valid:
            avg_ret = sum(a["peak_return_pct"] for a in valid) / len(valid)
            avg_wks = sum(a["weeks_to_peak"] for a in valid) / len(valid)
            topped = [a for a in valid if a.get("total_weeks")]
            avg_tot = sum(a["total_weeks"] for a in topped) / len(topped) if topped else None

            lines.append(f"    Avg peak : {avg_ret:+.0f}%  in {avg_wks:.1f} wks" +
                         (f"  |  avg run {avg_tot:.1f} wks" if avg_tot else ""))

            remaining = avg_wks - weeks_in
            if current_floor and anchor_ma and current_floor >= anchor_ma:
                if remaining > 1:
                    lines.append(
                        f"    ANALOG: wk {weeks_in:.1f} of ~{avg_wks:.0f} "
                        f"-> ~{remaining:.0f} wk(s) left if pattern holds."
                    )
                elif remaining < 0:
                    lines.append(
                        f"    ANALOG: past avg peak timing ({avg_wks:.0f} wks). Extended or failed."
                    )
                else:
                    lines.append("    ANALOG: near peak timing window.")
    else:
        lines.append("    No prior events for comparison.")

    return lines


def format_relationship(gc_20_50, gc_50_200, ma20, ma50, ma200) -> list[str]:
    """Render the cross-pair relationship block."""
    lines = ["", "  [ SIGNAL RELATIONSHIP ]"]

    has_short = gc_20_50 is not None
    has_long  = gc_50_200 is not None

    if has_short and has_long:
        d_short = datetime.strptime(gc_20_50["gc_date"], "%Y-%m-%d")
        d_long  = datetime.strptime(gc_50_200["gc_date"], "%Y-%m-%d")
        gap_wks = (d_short - d_long).days / 7

        if gap_wks > 0:
            lines.append(f"    20/50 fired {gap_wks:.1f} wks AFTER 50/200 (momentum lagging trend)")
        elif gap_wks < 0:
            lines.append(f"    20/50 fired {abs(gap_wks):.1f} wks BEFORE 50/200 (classic sequence)")
        else:
            lines.append("    20/50 and 50/200 fired on the same date")

        lines.append("    Both signals active -> double confirmed bullish alignment")

    elif has_short and not has_long:
        lines.append("    20/50 active  |  50/200 NOT yet confirmed within lookback")
        if ma50 and ma200:
            if ma50 > ma200:
                lines.append("    MA50 > MA200 currently -> long-term trend is bullish (50/200 GC may be older)")
            else:
                lines.append("    MA50 < MA200 currently -> long-term trend still bearish, 50/200 not confirmed")

    elif not has_short and has_long:
        lines.append("    50/200 active  |  20/50 not fired within lookback window")
        if ma20 and ma50:
            if ma20 > ma50:
                lines.append("    MA20 > MA50 currently -> short-term momentum is bullish (20/50 state OK)")
            else:
                lines.append("    MA20 < MA50 currently -> short-term momentum has cooled")

    # Current MA stack
    if ma20 and ma50 and ma200:
        stack = ma20 > ma50 > ma200
        lines.append(
            f"    MA stack: MA20 {'>' if ma20 > ma50 else '<'} MA50 "
            f"{'>' if ma50 > ma200 else '<'} MA200  "
            + ("-> fully aligned bullish" if stack else "-> stack not fully aligned")
        )

    return lines


def format_report(slug, chain, ranking, price_series,
                  gc_data_20_50, gc_data_50_200,
                  ma20, ma50, ma200) -> str:
    chain_sym = chain.upper()
    current_floor = price_series[-1][1] if price_series else None
    today = _now()

    sep = "=" * 58
    lines = [sep, f"  {slug.upper()}  ({chain_sym})   Ranking #{ranking}", sep, ""]

    # Current price state
    floor_str = f"{current_floor:.4f} {chain_sym}" if current_floor else "N/A"
    ma20_str  = f"{ma20:.4f}" if ma20 else "N/A"
    ma50_str  = f"{ma50:.4f}" if ma50 else "N/A"
    ma200_str = f"{ma200:.4f}" if ma200 else "N/A"
    lines.append(f"  Floor: {floor_str}   |   MA20: {ma20_str}   MA50: {ma50_str}   MA200: {ma200_str}")
    lines.append("")

    # 20/50 block
    if gc_data_20_50:
        cfg = MA_PAIRS["20/50"]
        wks = (today - datetime.strptime(gc_data_20_50["gc_date"], "%Y-%m-%d")).days / 7
        lines += format_pair_block("20/50", cfg, gc_data_20_50["current_gc"],
                                   gc_data_20_50["past_analyses"], wks,
                                   current_floor, ma50, chain_sym)
    else:
        lines.append("  [ GC 20/50 ]  no active signal within lookback window")
        if ma20 and ma50:
            pct = (ma20 - ma50) / ma50 * 100
            lines.append(f"    MA20 vs MA50: {pct:+.1f}%  ({'above' if pct >= 0 else 'below'})")

    lines.append("")

    # 50/200 block
    if gc_data_50_200:
        cfg = MA_PAIRS["50/200"]
        wks = (today - datetime.strptime(gc_data_50_200["gc_date"], "%Y-%m-%d")).days / 7
        lines += format_pair_block("50/200", cfg, gc_data_50_200["current_gc"],
                                   gc_data_50_200["past_analyses"], wks,
                                   current_floor, ma200, chain_sym)
    else:
        lines.append("  [ GC 50/200 ]  no active signal within lookback window")
        if ma50 and ma200:
            pct = (ma50 - ma200) / ma200 * 100
            lines.append(f"    MA50 vs MA200: {pct:+.1f}%  ({'above' if pct >= 0 else 'below'})")

    # Relationship block
    lines += format_relationship(gc_data_20_50, gc_data_50_200, ma20, ma50, ma200)

    lines.append("")
    return "\n".join(lines)


# ──────────────────────── DB persistence ────────────────────────

def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gc_pattern_analysis (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date                TEXT NOT NULL,
            slug                    TEXT NOT NULL,
            chain                   TEXT NOT NULL,
            ranking                 INTEGER,
            current_floor           REAL,
            ma20                    REAL,
            ma50                    REAL,
            ma200                   REAL,
            ma_stack_aligned        INTEGER,
            pair                    TEXT NOT NULL,
            gc_date                 TEXT,
            weeks_since_gc          REAL,
            floor_at_signal         REAL,
            anchor_ma               REAL,
            distance_from_anchor_pct REAL,
            prior_gc_count          INTEGER,
            runner_count            INTEGER,
            moderate_count          INTEGER,
            failed_count            INTEGER,
            avg_peak_return_pct     REAL,
            avg_weeks_to_peak       REAL,
            avg_total_run_weeks     REAL,
            analog_weeks_remaining  REAL,
            both_pairs_active       INTEGER,
            gap_weeks               REAL,
            created_at              TEXT,
            UNIQUE(run_date, slug, chain, pair)
        )
    """)
    conn.commit()


def save_pair_row(conn, run_date, slug, chain, ranking,
                  current_floor, ma20, ma50, ma200,
                  pair_label, pair_data, anchor_ma,
                  both_active, gap_weeks):
    today_str = _now().isoformat()

    if pair_data:
        gc_date = pair_data["gc_date"]
        weeks_since = (_now() - datetime.strptime(gc_date, "%Y-%m-%d")).days / 7
        floor_at_signal = pair_data["current_gc"]["floor_native"]
        dist = (current_floor - anchor_ma) / anchor_ma * 100 if (current_floor and anchor_ma) else None

        valid = [a for a in pair_data["past_analyses"] if a.get("outcome") != "NO_DATA"]
        prior_count   = len(valid)
        runner_count  = sum(1 for a in valid if a["outcome"] == "RUNNER")
        mod_count     = sum(1 for a in valid if a["outcome"] == "MODERATE")
        failed_count  = sum(1 for a in valid if a["outcome"] == "FAILED")
        avg_peak      = sum(a["peak_return_pct"] for a in valid) / len(valid) if valid else None
        avg_wks_peak  = sum(a["weeks_to_peak"]   for a in valid) / len(valid) if valid else None
        topped        = [a for a in valid if a.get("total_weeks")]
        avg_total     = sum(a["total_weeks"] for a in topped) / len(topped) if topped else None
        analog_rem    = (avg_wks_peak - weeks_since) if avg_wks_peak is not None else None
    else:
        gc_date = weeks_since = floor_at_signal = dist = None
        prior_count = runner_count = mod_count = failed_count = 0
        avg_peak = avg_wks_peak = avg_total = analog_rem = None

    ma_stack = int(bool(ma20 and ma50 and ma200 and ma20 > ma50 > ma200))

    conn.execute("""
        INSERT INTO gc_pattern_analysis (
            run_date, slug, chain, ranking,
            current_floor, ma20, ma50, ma200, ma_stack_aligned,
            pair, gc_date, weeks_since_gc, floor_at_signal,
            anchor_ma, distance_from_anchor_pct,
            prior_gc_count, runner_count, moderate_count, failed_count,
            avg_peak_return_pct, avg_weeks_to_peak, avg_total_run_weeks,
            analog_weeks_remaining, both_pairs_active, gap_weeks, created_at
        ) VALUES (
            ?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,  ?,?,  ?,?,?,?,  ?,?,?,  ?,?,?,?
        )
        ON CONFLICT(run_date, slug, chain, pair) DO UPDATE SET
            ranking                 = excluded.ranking,
            current_floor           = excluded.current_floor,
            ma20                    = excluded.ma20,
            ma50                    = excluded.ma50,
            ma200                   = excluded.ma200,
            ma_stack_aligned        = excluded.ma_stack_aligned,
            gc_date                 = excluded.gc_date,
            weeks_since_gc          = excluded.weeks_since_gc,
            floor_at_signal         = excluded.floor_at_signal,
            anchor_ma               = excluded.anchor_ma,
            distance_from_anchor_pct= excluded.distance_from_anchor_pct,
            prior_gc_count          = excluded.prior_gc_count,
            runner_count            = excluded.runner_count,
            moderate_count          = excluded.moderate_count,
            failed_count            = excluded.failed_count,
            avg_peak_return_pct     = excluded.avg_peak_return_pct,
            avg_weeks_to_peak       = excluded.avg_weeks_to_peak,
            avg_total_run_weeks     = excluded.avg_total_run_weeks,
            analog_weeks_remaining  = excluded.analog_weeks_remaining,
            both_pairs_active       = excluded.both_pairs_active,
            gap_weeks               = excluded.gap_weeks,
            created_at              = excluded.created_at
    """, (
        run_date, slug, chain, ranking,
        current_floor, ma20, ma50, ma200, ma_stack,
        pair_label, gc_date, weeks_since, floor_at_signal,
        anchor_ma, dist,
        prior_count, runner_count, mod_count, failed_count,
        avg_peak, avg_wks_peak, avg_total,
        analog_rem, int(both_active), gap_weeks, today_str,
    ))


# ──────────────────────── Main ────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analyze GC patterns (20/50 + 50/200) for top NFT collections")
    parser.add_argument("--ranking",   type=int,   default=MAX_RANKING,            help="Max ranking filter (default 150)")
    parser.add_argument("--lookback",  type=int,   default=ACTIVE_GC_LOOKBACK_DAYS, help="GC lookback window in days (default 180)")
    parser.add_argument("--min-weeks", type=float, default=0.0,                    help="Skip GCs fired less than N weeks ago")
    args = parser.parse_args()

    conn = get_db_connection()
    today = _now()
    run_date = today.strftime("%Y-%m-%d")

    ensure_table(conn)

    print(f"\nScanning GC signals (20/50 + 50/200) | last {args.lookback} days | ranking <= {args.ranking}\n")

    # Build index of recent GCs per pair: (slug, chain) -> gc_date
    pair_index = {}
    for pair_label, cfg in MA_PAIRS.items():
        recs = get_recent_active_gcs_for_pair(conn, args.lookback, cfg["short"], cfg["long"])
        for r in recs:
            key = (r["slug"], r["chain"])
            pair_index.setdefault(key, {})[pair_label] = r["gc_date"]

    # Collect all unique (slug, chain) that have at least one active GC
    all_keys = list(pair_index.keys())
    print(f"  Collections with any recent GC (unfiltered): {len(all_keys)}")

    results = []
    for (slug, chain) in all_keys:
        ranking = get_latest_ranking(conn, slug, chain)
        if ranking is None or ranking > args.ranking:
            continue

        # Check min-weeks against the most recent GC across both pairs
        gc_dates = list(pair_index[(slug, chain)].values())
        most_recent = max(datetime.strptime(d, "%Y-%m-%d") for d in gc_dates)
        weeks_since_most_recent = (today - most_recent).days / 7
        if weeks_since_most_recent < args.min_weeks:
            continue

        price_series = get_price_series(conn, slug, chain)
        if len(price_series) < 200:  # need at least 200 data points for MA200
            continue

        ma20  = compute_ma(price_series, 20,  ALL_MA_PERIODS[20])
        ma50  = compute_ma(price_series, 50,  ALL_MA_PERIODS[50])
        ma200 = compute_ma(price_series, 200, ALL_MA_PERIODS[200])

        pair_gcs = pair_index[(slug, chain)]

        def build_pair_data(pair_label):
            if pair_label not in pair_gcs:
                return None
            gc_date_str = pair_gcs[pair_label]
            cfg = MA_PAIRS[pair_label]
            all_evts = get_all_gc_events(conn, slug, chain, cfg["short"], cfg["long"])
            current_gc = next((g for g in reversed(all_evts) if g["date"] == gc_date_str), None)
            if not current_gc:
                return None
            past_gcs = [g for g in all_evts if g["date"] < gc_date_str]
            past_analyses = [analyze_past_gc(price_series, g["date"]) for g in past_gcs]
            return {"gc_date": gc_date_str, "current_gc": current_gc, "past_analyses": past_analyses}

        gc_20_50  = build_pair_data("20/50")
        gc_50_200 = build_pair_data("50/200")

        results.append({
            "slug": slug, "chain": chain, "ranking": ranking,
            "price_series": price_series,
            "gc_20_50": gc_20_50, "gc_50_200": gc_50_200,
            "ma20": ma20, "ma50": ma50, "ma200": ma200,
        })

    results.sort(key=lambda x: x["ranking"])
    print(f"  Qualifying collections (ranking <= {args.ranking}): {len(results)}\n")

    saved = 0
    for r in results:
        slug, chain = r["slug"], r["chain"]
        gc_20_50, gc_50_200 = r["gc_20_50"], r["gc_50_200"]

        both_active = gc_20_50 is not None and gc_50_200 is not None
        gap_weeks = None
        if both_active:
            d_short = datetime.strptime(gc_20_50["gc_date"], "%Y-%m-%d")
            d_long  = datetime.strptime(gc_50_200["gc_date"], "%Y-%m-%d")
            gap_weeks = (d_long - d_short).days / 7  # positive = 20/50 fired first

        save_pair_row(conn, run_date, slug, chain, r["ranking"],
                      r["price_series"][-1][1] if r["price_series"] else None,
                      r["ma20"], r["ma50"], r["ma200"],
                      "20/50", gc_20_50, r["ma50"],
                      both_active, gap_weeks)

        save_pair_row(conn, run_date, slug, chain, r["ranking"],
                      r["price_series"][-1][1] if r["price_series"] else None,
                      r["ma20"], r["ma50"], r["ma200"],
                      "50/200", gc_50_200, r["ma200"],
                      both_active, gap_weeks)

        saved += 1

        report = format_report(
            slug, chain, r["ranking"], r["price_series"],
            gc_20_50, gc_50_200,
            r["ma20"], r["ma50"], r["ma200"],
        )
        print(report)

    conn.commit()
    conn.close()
    print(f"  Saved {saved * 2} rows ({saved} collections x 2 pairs) to gc_pattern_analysis for run_date={run_date}")


if __name__ == "__main__":
    main()
