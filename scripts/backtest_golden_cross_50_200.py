"""
Backtest Golden Cross 50/200 — NFT Collections
================================================
Analizza tutti i segnali di Golden Cross 50MA / 200MA storici e misura
la performance per diverse strategie di ingresso e uscita.

FILTRI APPLICATI:
  - Escluse collezioni con categoria "art" (low-supply, illiquide)
  - Escluse collezioni con total_supply < MIN_SUPPLY (se dato disponibile)

SEGMENTAZIONE per fascia di floor price al momento della GC:
  - Micro  : < 0.1  ETH
  - Low    : 0.1 – 0.3 ETH
  - Mid    : 0.3 – 1.0 ETH
  - High   : 1.0 – 5.0 ETH
  - Blue   : > 5.0 ETH

GRIGLIA di analisi:
  - ENTRY DELAY : 0, 1, 3, 7, 14, 30 giorni dopo il segnale GC
  - HOLD PERIOD : 7, 14, 30, 60, 90, 120, 180 giorni dopo l'ingresso
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection

import logging
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

# ─────────────────────────────────────────────
# Configurazione griglia backtest
# ─────────────────────────────────────────────
ENTRY_DELAYS = [0, 1, 3, 7, 14, 30]      # giorni dopo il segnale GC
HOLD_PERIODS  = [7, 14, 30, 60, 90, 120, 180]  # giorni di holding dopo l'ingresso

# Minimo di trade richiesti per considerare una cella valida
MIN_TRADES = 5

# Usa solo native floor price — più stabile dell'USD
USE_NATIVE = True

# ── Filtri ──────────────────────────────────
# Escludi collezioni la cui categoria contiene "art"
EXCLUDE_ART = True

# Escludi collezioni con total_supply < MIN_SUPPLY (0 = disabilitato)
MIN_SUPPLY = 500

# ── Fasce di prezzo native (ETH o equivalente) ──
PRICE_BANDS = [
    ("Micro  (< 0.1)",   0.0,   0.1),
    ("Low    (0.1-0.3)", 0.1,   0.3),
    ("Mid    (0.3-1.0)", 0.3,   1.0),
    ("High   (1.0-5.0)", 1.0,   5.0),
    ("Blue   (> 5.0)",   5.0,   float("inf")),
]

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def date_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def get_price_band(floor_native: float) -> str:
    """Ritorna l'etichetta della fascia di prezzo."""
    for label, lo, hi in PRICE_BANDS:
        if lo <= floor_native < hi:
            return label
    return "Unknown"


def load_excluded_slugs(conn: sqlite3.Connection) -> set:
    """
    Costruisce il set di (slug, chain) da escludere:
      - collezioni con categoria contenente 'art'
      - collezioni con total_supply < MIN_SUPPLY (se disponibile)
    """
    excluded = set()
    cur = conn.cursor()

    if EXCLUDE_ART:
        cur.execute("""
            SELECT slug, chain FROM nft_collections
            WHERE categories LIKE '%art%'
        """)
        art_set = {(r[0], r[1]) for r in cur.fetchall()}
        excluded |= art_set
        logging.info(f"  Escluse per categoria 'art': {len(art_set)} collezioni")

    if MIN_SUPPLY > 0:
        cur.execute("""
            SELECT slug, chain, MAX(total_supply) as max_supply
            FROM historical_nft_data
            WHERE total_supply IS NOT NULL
            GROUP BY slug, chain
            HAVING max_supply < ?
        """, (MIN_SUPPLY,))
        low_supply_set = {(r[0], r[1]) for r in cur.fetchall()}
        before = len(excluded)
        excluded |= low_supply_set
        logging.info(f"  Escluse per supply < {MIN_SUPPLY}: {len(excluded) - before} aggiuntive")

    return excluded


def load_golden_crosses(conn: sqlite3.Connection, excluded: set) -> list[dict]:
    """Carica tutti i segnali GC 50/200, escludendo i filtri."""
    cur = conn.cursor()
    cur.execute("""
        SELECT slug, chain, date, floor_native, floor_usd
        FROM historical_golden_crosses
        WHERE ma_short_period = 50
          AND ma_long_period  = 200
        ORDER BY date
    """)
    rows = cur.fetchall()
    result = []
    filtered_out = 0
    for r in rows:
        slug, chain = r[0], r[1]
        if (slug, chain) in excluded:
            filtered_out += 1
            continue
        floor = r[2]  # date
        result.append({
            "slug":         r[0],
            "chain":        r[1],
            "date":         r[2],
            "floor_native": r[3],
            "floor_usd":    r[4],
            "price_band":   get_price_band(r[3]) if r[3] else "Unknown",
        })
    logging.info(f"  Segnali filtrati (art/low-supply): {filtered_out}")
    return result


def load_prices(conn: sqlite3.Connection) -> dict:
    """
    Carica tutte le floor price da historical_nft_data.
    Ritorna un dict: {(slug, chain): {date_str: floor_native}}
    """
    cur = conn.cursor()
    col = "floor_native" if USE_NATIVE else "floor_usd"
    cur.execute(f"""
        SELECT slug, chain, latest_floor_date, {col}
        FROM historical_nft_data
        WHERE {col} IS NOT NULL AND {col} > 0
        ORDER BY slug, chain, latest_floor_date
    """)
    prices: dict = defaultdict(dict)
    for slug, chain, d, price in cur.fetchall():
        prices[(slug, chain)][d] = price
    return dict(prices)


def get_price_near(price_map: dict, target_date: datetime, window: int = 5):
    """
    Trova il prezzo più vicino a target_date (±window giorni).
    Ritorna (date_effettiva, prezzo) o None se non trovato.
    """
    for delta in range(window + 1):
        for sign in ([0] if delta == 0 else [1, -1]):
            d = date_str(target_date + timedelta(days=delta * sign))
            if d in price_map:
                return d, price_map[d]
    return None


# ─────────────────────────────────────────────
# Core backtest
# ─────────────────────────────────────────────

def compute_stats(rets: list) -> dict | None:
    n = len(rets)
    if n < MIN_TRADES:
        return None
    sorted_rets = sorted(rets)
    top10_cut = max(1, int(n * 0.10))
    bot10_cut = max(1, int(n * 0.10))
    return {
        "n_trades"       : n,
        "win_rate"       : sum(1 for r in rets if r > 0) / n * 100,
        "avg_return"     : statistics.mean(rets),
        "median_return"  : statistics.median(rets),
        "best_10pct_avg" : statistics.mean(sorted_rets[-top10_cut:]),
        "worst_10pct_avg": statistics.mean(sorted_rets[:bot10_cut]),
        "pct_gt_20"      : sum(1 for r in rets if r >  20) / n * 100,
        "pct_gt_50"      : sum(1 for r in rets if r >  50) / n * 100,
        "pct_lt_minus20" : sum(1 for r in rets if r < -20) / n * 100,
    }


def run_backtest_raw(golden_crosses: list[dict], prices: dict) -> list[dict]:
    """Ritorna la lista completa di tutti i trade con metadati (band inclusa)."""
    today = datetime.now()
    raw = []

    for gc in golden_crosses:
        slug    = gc["slug"]
        chain   = gc["chain"]
        band    = gc["price_band"]
        gc_date = datetime.strptime(gc["date"], "%Y-%m-%d")
        pm = prices.get((slug, chain))
        if pm is None:
            continue

        for entry_delay in ENTRY_DELAYS:
            entry_target = gc_date + timedelta(days=entry_delay)
            if entry_target > today:
                continue
            entry_result = get_price_near(pm, entry_target)
            if entry_result is None:
                continue
            _, entry_price = entry_result

            for hold_period in HOLD_PERIODS:
                exit_target = entry_target + timedelta(days=hold_period)
                if exit_target > today:
                    continue
                exit_result = get_price_near(pm, exit_target)
                if exit_result is None:
                    continue
                _, exit_price = exit_result

                raw.append({
                    "slug"        : slug,
                    "chain"       : chain,
                    "price_band"  : band,
                    "gc_date"     : gc["date"],
                    "entry_delay" : entry_delay,
                    "hold_period" : hold_period,
                    "entry_price" : entry_price,
                    "exit_price"  : exit_price,
                    "return_pct"  : (exit_price - entry_price) / entry_price * 100.0,
                })

    skipped_future = sum(1 for gc in golden_crosses
                         for ed in ENTRY_DELAYS
                         if datetime.strptime(gc["date"], "%Y-%m-%d") + timedelta(days=ed) > today)
    logging.info(f"Skipped (future entry): ~{skipped_future}")
    return raw


def aggregate_results(raw_trades: list[dict], band_filter: str | None = None) -> dict:
    """
    Aggrega i raw_trades in una griglia (entry_delay, hold_period) → stats.
    Se band_filter è specificato, usa solo i trade di quella banda.
    """
    grid: dict = defaultdict(list)
    for t in raw_trades:
        if band_filter is not None and t["price_band"] != band_filter:
            continue
        grid[(t["entry_delay"], t["hold_period"])].append(t["return_pct"])
    return {k: compute_stats(v) for k, v in grid.items()}


# ─────────────────────────────────────────────
# Stampa risultati
# ─────────────────────────────────────────────

def print_summary_table(results: dict, title: str = ""):
    """Stampa la griglia entry_delay × hold_period per ogni metrica chiave."""
    metrics = [
        ("median_return", "Rendimento Mediano (%)"),
        ("avg_return",    "Rendimento Medio (%)"),
        ("win_rate",      "Win Rate (%)"),
        ("pct_gt_20",     "% trade > +20%"),
        ("pct_gt_50",     "% trade > +50%"),
        ("pct_lt_minus20","% trade < -20%"),
        ("n_trades",      "N° Trade"),
    ]
    col_w = 10

    if title:
        print(f"\n{'█'*80}")
        print(f"  {title}")
        print(f"{'█'*80}")

    for metric_key, metric_label in metrics:
        print(f"\n{'═'*80}")
        print(f"  {metric_label}")
        print(f"{'─'*80}")
        entry_hold_label = "Entry\\Hold"
        header = f"{entry_hold_label:>12}" + "".join(f"{str(hp)+'d':>{col_w}}" for hp in HOLD_PERIODS)
        print(header)
        print("─" * len(header))

        for ed in ENTRY_DELAYS:
            row = f"{'GC+'+str(ed)+'d':>12}"
            for hp in HOLD_PERIODS:
                v = results.get((ed, hp))
                if v is None:
                    row += f"{'N/A':>{col_w}}"
                else:
                    val = v[metric_key]
                    row += f"{int(val):>{col_w}}" if metric_key == "n_trades" else f"{val:>{col_w}.1f}"
            print(row)


def find_best_strategy(results: dict, label: str = ""):
    """Trova e stampa la combinazione con il miglior rendimento mediano e win rate."""
    valid = {k: v for k, v in results.items() if v is not None}
    if not valid:
        print("  (dati insufficienti per questa fascia)")
        return

    best_med  = max(valid.items(), key=lambda x: x[1]["median_return"])
    best_win  = max(valid.items(), key=lambda x: x[1]["win_rate"])
    # Score bilanciato: mediana × win_rate (ignora outlier)
    best_bal  = max(valid.items(), key=lambda x: x[1]["median_return"] * x[1]["win_rate"] / 100
                    if x[1]["median_return"] > 0 else -9999)

    if label:
        print(f"\n{'─'*80}")
        print(f"  >>> OTTIMALI per {label}")

    def show(tag, key_combo, stats):
        ed, hp = key_combo
        sign = "+" if stats["median_return"] >= 0 else ""
        print(f"    [{tag}] GC+{ed}d → hold {hp}d  |  "
              f"Mediana: {sign}{stats['median_return']:.1f}%  "
              f"Win: {stats['win_rate']:.1f}%  "
              f"N={stats['n_trades']}  "
              f">+20%: {stats['pct_gt_20']:.1f}%  "
              f"<-20%: {stats['pct_lt_minus20']:.1f}%")

    show("Miglior Mediana", best_med[0], best_med[1])
    show("Miglior Win Rate", best_win[0], best_win[1])
    if best_bal[0] != best_med[0]:
        show("Miglior Bilanciato", best_bal[0], best_bal[1])


def print_top_trades(raw_trades: list[dict], entry_delay: int, hold_period: int,
                     band_filter: str | None = None, top_n: int = 20):
    """Mostra i migliori N trade per la strategia selezionata."""
    rows = [r for r in raw_trades
            if r["entry_delay"] == entry_delay and r["hold_period"] == hold_period
            and (band_filter is None or r["price_band"] == band_filter)]
    rows_sorted = sorted(rows, key=lambda x: x["return_pct"], reverse=True)

    band_str = f" [{band_filter}]" if band_filter else ""
    print(f"\n{'═'*80}")
    print(f"  TOP {top_n} TRADE — Entry: GC+{entry_delay}d  |  Hold: {hold_period}d{band_str}")
    print(f"{'─'*80}")
    print(f"{'Slug':<38} {'GC Date':>10} {'Entry':>9} {'Exit':>9} {'Return%':>9}")
    print("─" * 80)
    for r in rows_sorted[:top_n]:
        print(f"{r['slug']:<38} {r['gc_date']:>10} "
              f"{r['entry_price']:>9.4f} {r['exit_price']:>9.4f} {r['return_pct']:>9.1f}%")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    setup_logging()
    logging.info("=== Backtest Golden Cross 50/200 avviato ===")

    conn = get_db_connection()

    logging.info("Carico filtri collezioni...")
    excluded = load_excluded_slugs(conn)
    logging.info(f"  Totale escluse: {len(excluded)}")

    logging.info("Carico segnali GC 50/200...")
    golden_crosses = load_golden_crosses(conn, excluded)
    logging.info(f"  {len(golden_crosses)} segnali dopo filtri")

    logging.info("Carico storico prezzi...")
    prices = load_prices(conn)
    conn.close()

    logging.info("Calcolo raw trades...")
    raw_trades = run_backtest_raw(golden_crosses, prices)
    logging.info(f"  {len(raw_trades)} trade totali analizzati")

    # ── Header report ──────────────────────────────────────────────────────
    bands_present = sorted({t["price_band"] for t in raw_trades})
    filter_str = "art escluse" + (f" | supply ≥ {MIN_SUPPLY}" if MIN_SUPPLY else "")

    print(f"\n\n{'█'*80}")
    print(f"  BACKTEST GOLDEN CROSS 50/200 — NFT Floor Price (native)")
    print(f"  Filtri: {filter_str}")
    print(f"  Segnali GC: {len(golden_crosses)} | Trade: {len(raw_trades)}")
    print(f"{'█'*80}")

    # ── 1. Risultati globali (tutti i segmenti) ────────────────────────────
    results_all = aggregate_results(raw_trades)
    print_summary_table(results_all, "GLOBALE (no art, supply filtrata)")
    find_best_strategy(results_all, "GLOBALE")

    # ── 2. Risultati per fascia di prezzo ─────────────────────────────────
    print(f"\n\n{'█'*80}")
    print("  ANALISI PER FASCIA DI FLOOR PRICE AL MOMENTO DELLA GC")
    print(f"{'█'*80}")

    for band_label, lo, hi in PRICE_BANDS:
        results_band = aggregate_results(raw_trades, band_filter=band_label)
        n_total = sum(v["n_trades"] for v in results_band.values() if v) // len(HOLD_PERIODS) or 0
        print_summary_table(results_band, f"FASCIA: {band_label}  (~{n_total} segnali)")
        find_best_strategy(results_band, band_label)

    # ── 3. Top trade per strategia migliore globale ────────────────────────
    valid_all = {k: v for k, v in results_all.items() if v is not None}
    if valid_all:
        best_key = max(valid_all.items(), key=lambda x: x[1]["median_return"])[0]
        ed_best, hp_best = best_key
        print_top_trades(raw_trades, ed_best, hp_best, top_n=25)

    # ── 4. Riepilogo fasce ─────────────────────────────────────────────────
    print(f"\n\n{'█'*80}")
    print("  RIEPILOGO COMPARATIVO FASCE — Strategia GC+7d / hold 30d")
    print(f"{'█'*80}")
    print(f"{'Fascia':<25} {'N':>6} {'Mediana%':>10} {'WinRate%':>10} {'>+20%':>8} {'<-20%':>8}")
    print("─" * 70)
    for band_label, lo, hi in PRICE_BANDS:
        res = aggregate_results(raw_trades, band_filter=band_label)
        v = res.get((7, 30))
        if v:
            print(f"{band_label:<25} {v['n_trades']:>6} {v['median_return']:>10.1f} "
                  f"{v['win_rate']:>10.1f} {v['pct_gt_20']:>8.1f} {v['pct_lt_minus20']:>8.1f}")
        else:
            print(f"{band_label:<25} {'N/A':>6}")

    logging.info("=== Backtest completato ===")


if __name__ == "__main__":
    main()
