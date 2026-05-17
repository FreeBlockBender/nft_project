"""
Estrai Golden Cross 50/200 — Blue Chip e Mid — ultimi 6 mesi CON SUCCESSO
==========================================================================
Strategia applicata dai risultati del backtest:
  - Blue Chip (> 5 ETH)  : entry GC+14d, hold 60d
  - Mid       (0.3-1 ETH): entry GC+7d,  hold 30d

Periodo: ultimi 6 mesi da oggi
Filtri:  no art, supply >= 500
Successo: rendimento > 0%  (mostra anche il % effettivo)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection

import logging
from datetime import datetime, timedelta
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────────────
MONTHS_BACK   = 6
MIN_SUPPLY    = 500
EXCLUDE_ART   = True

# Strategia ottimale per fascia (dal backtest)
STRATEGIES = {
    "Blue Chip (> 5 ETH)": {
        "floor_lo": 5.0,
        "floor_hi": float("inf"),
        "entry_delay": 14,
        "hold_days":   60,
    },
    "Mid (0.3-1 ETH)": {
        "floor_lo": 0.3,
        "floor_hi": 1.0,
        "entry_delay": 7,
        "hold_days":   30,
    },
}


def load_excluded_slugs(conn):
    excluded = set()
    cur = conn.cursor()
    if EXCLUDE_ART:
        cur.execute("SELECT slug, chain FROM nft_collections WHERE categories LIKE '%art%'")
        excluded |= {(r[0], r[1]) for r in cur.fetchall()}
    if MIN_SUPPLY > 0:
        cur.execute("""
            SELECT slug, chain FROM historical_nft_data
            WHERE total_supply IS NOT NULL
            GROUP BY slug, chain
            HAVING MAX(total_supply) < ?
        """, (MIN_SUPPLY,))
        excluded |= {(r[0], r[1]) for r in cur.fetchall()}
    return excluded


def load_prices(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT slug, chain, latest_floor_date, floor_native
        FROM historical_nft_data
        WHERE floor_native IS NOT NULL AND floor_native > 0
    """)
    prices = defaultdict(dict)
    for slug, chain, d, price in cur.fetchall():
        prices[(slug, chain)][d] = price
    return dict(prices)


def get_price_near(price_map, target_date, window=5):
    for delta in range(window + 1):
        for sign in ([0] if delta == 0 else [1, -1]):
            d = (target_date + timedelta(days=delta * sign)).strftime("%Y-%m-%d")
            if d in price_map:
                return d, price_map[d]
    return None


def main():
    setup_logging()
    logging.info("=== Estrazione GC vincenti Blue Chip + Mid (ultimi 6 mesi) ===")

    today    = datetime.now()
    from_date = today - timedelta(days=MONTHS_BACK * 30)

    conn = get_db_connection()
    excluded = load_excluded_slugs(conn)

    cur = conn.cursor()
    cur.execute("""
        SELECT slug, chain, date, floor_native
        FROM historical_golden_crosses
        WHERE ma_short_period = 50
          AND ma_long_period  = 200
          AND date >= ?
        ORDER BY date DESC
    """, (from_date.strftime("%Y-%m-%d"),))
    gcs = [{"slug": r[0], "chain": r[1], "date": r[2], "floor_native": r[3]}
           for r in cur.fetchall()
           if (r[0], r[1]) not in excluded and r[3] is not None]

    logging.info(f"GC negli ultimi 6 mesi (dopo filtri): {len(gcs)}")

    prices = load_prices(conn)
    conn.close()

    results = {label: [] for label in STRATEGIES}

    for gc in gcs:
        floor = gc["floor_native"]
        gc_date = datetime.strptime(gc["date"], "%Y-%m-%d")
        pm = prices.get((gc["slug"], gc["chain"]))
        if pm is None:
            continue

        for label, cfg in STRATEGIES.items():
            if not (cfg["floor_lo"] <= floor < cfg["floor_hi"]):
                continue

            entry_target = gc_date + timedelta(days=cfg["entry_delay"])
            exit_target  = entry_target + timedelta(days=cfg["hold_days"])

            entry_r = get_price_near(pm, entry_target)
            exit_r  = get_price_near(pm, exit_target)

            entry_date_found = entry_r[0] if entry_r else None
            exit_date_found  = exit_r[0]  if exit_r  else None
            entry_price      = entry_r[1] if entry_r else None
            exit_price       = exit_r[1]  if exit_r  else None

            if entry_price is None:
                status = "no data"
                ret    = None
            elif exit_price is None:
                # Posizione ancora aperta
                status = "OPEN"
                ret    = None
            else:
                ret = (exit_price - entry_price) / entry_price * 100.0
                status = "WIN" if ret > 0 else "LOSS"

            results[label].append({
                "slug"        : gc["slug"],
                "chain"       : gc["chain"],
                "gc_date"     : gc["date"],
                "floor_gc"    : floor,
                "entry_date"  : entry_date_found,
                "exit_date"   : exit_date_found,
                "entry_price" : entry_price,
                "exit_price"  : exit_price,
                "return_pct"  : ret,
                "status"      : status,
            })

    # ── Stampa risultati ──────────────────────────────────────────────────────
    for label, trades in results.items():
        wins  = [t for t in trades if t["status"] == "WIN"]
        losses= [t for t in trades if t["status"] == "LOSS"]
        opens = [t for t in trades if t["status"] == "OPEN"]
        nodat = [t for t in trades if t["status"] == "no data"]

        print(f"\n{'█'*80}")
        print(f"  {label}")
        print(f"  Periodo: {from_date.strftime('%Y-%m-%d')} → {today.strftime('%Y-%m-%d')}")
        cfg = STRATEGIES[label]
        print(f"  Strategia: entra GC+{cfg['entry_delay']}d, esci dopo {cfg['hold_days']}d")
        print(f"  Totale segnali: {len(trades)}  |  WIN: {len(wins)}  |  LOSS: {len(losses)}  |  OPEN: {len(opens)}  |  No data: {len(nodat)}")
        if wins or losses:
            closed = wins + losses
            win_rate = len(wins) / len(closed) * 100 if closed else 0
            avg_ret  = sum(t["return_pct"] for t in closed) / len(closed) if closed else 0
            print(f"  Win Rate (chiusi): {win_rate:.1f}%  |  Avg return: {avg_ret:.1f}%")
        print(f"{'█'*80}")

        # WIN ─────────────────────────────────────────────────────────────────
        if wins:
            wins_sorted = sorted(wins, key=lambda x: x["return_pct"], reverse=True)
            print(f"\n  ✅ VINCENTI ({len(wins)})")
            print(f"  {'Slug':<40} {'GC Date':>10} {'Floor GC':>9} {'Entry':>8} {'Exit':>8} {'Return%':>9}  Periodo")
            print("  " + "─"*100)
            for t in wins_sorted:
                print(f"  {t['slug']:<40} {t['gc_date']:>10} {t['floor_gc']:>9.3f} "
                      f"{t['entry_price']:>8.3f} {t['exit_price']:>8.3f} "
                      f"{t['return_pct']:>+9.1f}%  "
                      f"{t['entry_date'] or '?'} → {t['exit_date'] or '?'}")

        # OPEN ────────────────────────────────────────────────────────────────
        if opens:
            print(f"\n  🔵 ANCORA APERTE — entra oggi o attendi scadenza ({len(opens)})")
            print(f"  {'Slug':<40} {'GC Date':>10} {'Floor GC':>9} {'Entry Price':>12} {'Entry Date':>12}")
            print("  " + "─"*90)
            for t in opens:
                ep = f"{t['entry_price']:.3f}" if t["entry_price"] else "N/A"
                print(f"  {t['slug']:<40} {t['gc_date']:>10} {t['floor_gc']:>9.3f} "
                      f"{ep:>12}  {t['entry_date'] or 'N/A':>12}")

        # LOSS ────────────────────────────────────────────────────────────────
        if losses:
            losses_sorted = sorted(losses, key=lambda x: x["return_pct"])
            print(f"\n  ❌ PERDENTI ({len(losses)})")
            print(f"  {'Slug':<40} {'GC Date':>10} {'Floor GC':>9} {'Entry':>8} {'Exit':>8} {'Return%':>9}")
            print("  " + "─"*95)
            for t in losses_sorted:
                print(f"  {t['slug']:<40} {t['gc_date']:>10} {t['floor_gc']:>9.3f} "
                      f"{t['entry_price']:>8.3f} {t['exit_price']:>8.3f} "
                      f"{t['return_pct']:>+9.1f}%")

    logging.info("=== Estrazione completata ===")


if __name__ == "__main__":
    main()
