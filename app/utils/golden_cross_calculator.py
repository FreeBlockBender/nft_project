import sqlite3
from datetime import datetime, timedelta
from app.utils.moving_average import calculate_sma, is_golden_cross
from app.config import load_config

config = load_config()
db_path = config.get("DB_PATH", "nft_data.sqlite3")

# PARAMETRI SMA
MA_SHORT = 50
MA_LONG = 200
MISSING_THRESH = 3  # numero massimo giorni mancanti consentiti

def get_collections(conn):
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier, slug, chain FROM nft_collections")
    return cur.fetchall()  # lista di tuple (identifier, slug, chain)

def get_floor_series(conn, collection_id, floor_field):
    cur = conn.cursor()
    cur.execute(
        f"SELECT latest_floor_date, {floor_field} FROM historical_nft_data "
        "WHERE collection_identifier = ? AND {0} IS NOT NULL "
        "ORDER BY latest_floor_date ASC".format(floor_field),
        (collection_id,)
    )
    return cur.fetchall()  # lista (date, valore)

def get_floor_usd_and_native(conn, collection_id, date):
    cur = conn.cursor()
    cur.execute(
        "SELECT floor_native, floor_usd FROM historical_nft_data "
        "WHERE collection_identifier = ? AND latest_floor_date = ?", (collection_id, date)
    )
    return cur.fetchone() or (None, None)

def golden_cross_for_collection(
    conn, collection_id, slug, chain, floor_field, is_native, idx, total
):
    serie = get_floor_series(conn, collection_id, floor_field)
    if len(serie) < MA_LONG + 1:
        print(f"  {slug} ({collection_id}): dati insufficienti per calcolo su {floor_field}")
        return 0

    # Prendo solo le date come riferimento (ordinate)
    date_list = [d for d, v in serie]
    crosses_found = 0

    for i in range(MA_LONG, len(date_list)):
        date_today = date_list[i]
        date_yest = date_list[i-1]
        # Ricavo SMA giorno x e giorno x-1
        ma_short_today = calculate_sma(serie[:i+1], MA_SHORT, date_today, MISSING_THRESH)
        ma_long_today = calculate_sma(serie[:i+1], MA_LONG, date_today, MISSING_THRESH)
        ma_short_yesterday = calculate_sma(serie[:i], MA_SHORT, date_yest, MISSING_THRESH)
        ma_long_yesterday = calculate_sma(serie[:i], MA_LONG, date_yest, MISSING_THRESH)

        # Golden cross?
        if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
            # floor_native/floor_usd del giorno sul record principale (ricava entrambi per inserirli sempre)
            floor_native, floor_usd = get_floor_usd_and_native(conn, collection_id, date_today)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO historical_golden_crosses 
                (collection_identifier, chain, date, inserted_ts, is_native, floor_native, floor_usd,
                 ma_short, ma_long, ma_short_previous_day, ma_long_previous_day, ma_short_period, ma_long_period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (collection_id, chain, date_today, datetime.utcnow().isoformat(), 
                  int(is_native), floor_native, floor_usd,
                  ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday,
                  MA_SHORT, MA_LONG))
            crosses_found += 1

    print(f"[{idx}/{total}] {slug} ({collection_id}) - {floor_field} : Golden Cross trovate: {crosses_found}")
    return crosses_found

def main():
    conn = sqlite3.connect(db_path)
    collections = get_collections(conn)
    total = len(collections)
    gc_total = 0

    for idx, (collection_id, slug, chain) in enumerate(collections, 1):
        # Native
        print(f"\n[{idx}/{total}] {slug} ({collection_id}) - Calcolo Golden Cross SU FLOOR_NATIVE")
        gc_native = golden_cross_for_collection(
            conn, collection_id, slug, chain, "floor_native", True, idx, total
        )
        # USD
        print(f"[{idx}/{total}] {slug} ({collection_id}) - Calcolo Golden Cross SU FLOOR_USD")
        gc_usd = golden_cross_for_collection(
            conn, collection_id, slug, chain, "floor_usd", False, idx, total
        )
        gc_total += gc_native + gc_usd

    conn.commit()
    conn.close()
    print(f"\nProcesso completato: Golden Cross individuate e registrate totali: {gc_total}")

if __name__ == "__main__":
    main()