import sqlite3
from datetime import datetime
from app.utils.moving_average import calculate_sma, is_golden_cross
from app.config import load_config

# Carica configurazione e parametri da .env
config = load_config()
db_path = config.get("DB_PATH", "nft_data.sqlite3")
MA_SHORT = int(config["SHORT_SMA"])
MA_LONG = int(config["LONG_SMA"])
SMA_50_MISSING_THRESH = int(config["SMA_50_MISSING_THRESH"])
SMA_200_MISSING_THRESH = int(config["SMA_200_MISSING_THRESH"])

def get_collections(conn):
    """Recupera tutte le collezioni NFT dal DB."""
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier, slug, chain FROM nft_collections")
    return cur.fetchall()  # lista di tuple (identifier, slug, chain)

def get_floor_series(conn, collection_id, floor_field):
    """Recupera la serie storica del floor price scelto (nativo/usd)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT latest_floor_date, {floor_field} FROM historical_nft_data "
        f"WHERE collection_identifier = ? AND {floor_field} IS NOT NULL "
        "ORDER BY latest_floor_date ASC",
        (collection_id,)
    )
    return cur.fetchall()  # lista (date, valore)

def get_floor_usd_and_native(conn, collection_id, date):
    """Recupera floor_native e floor_usd per una specifica collezione/data."""
    cur = conn.cursor()
    cur.execute(
        "SELECT floor_native, floor_usd FROM historical_nft_data "
        "WHERE collection_identifier = ? AND latest_floor_date = ?",
        (collection_id, date)
    )
    return cur.fetchone() or (None, None)

def insert_golden_cross(conn, collection_id, chain, date, is_native,
                        floor_native, floor_usd,
                        ma_short_today, ma_long_today,
                        ma_short_yesterday, ma_long_yesterday,
                        short_period, long_period):
    """Inserisce una Golden Cross nella tabella dedicata."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO historical_golden_crosses 
        (collection_identifier, chain, date, inserted_ts, is_native, floor_native, floor_usd,
         ma_short, ma_long, ma_short_previous_day, ma_long_previous_day, ma_short_period, ma_long_period)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (collection_id, chain, date, datetime.utcnow().isoformat(), int(is_native),
          floor_native, floor_usd,
          ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday,
          short_period, long_period))

# ======= FUNZIONE 1: Golden Cross storiche su tutta la serie =======
def detect_all_historical_golden_crosses(conn):
    """
    Scorre TUTTA la serie storica di ogni collezione e inserisce TUTTE le Golden Cross presenti.
    """
    collections = get_collections(conn)
    total = len(collections)
    gc_total = 0

    for idx, (collection_id, slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")

        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, collection_id, floor_field)
            short_period = MA_SHORT
            long_period = MA_LONG
            crosses_found = 0

            if len(serie) < long_period + 1:
                print(f"[{idx}/{total}] {slug}: dati insufficienti per la media mobile ({floor_field})")
                continue

            date_list = [d for d, v in serie]

            for i in range(long_period, len(date_list)):
                date_today = date_list[i]
                date_yesterday = date_list[i-1]

                # Soglie diverse
                ma_short_today = calculate_sma(serie[:i+1], short_period, date_today, SMA_50_MISSING_THRESH)
                ma_long_today = calculate_sma(serie[:i+1], long_period, date_today, SMA_200_MISSING_THRESH)
                ma_short_yesterday = calculate_sma(serie[:i], short_period, date_yesterday, SMA_50_MISSING_THRESH)
                ma_long_yesterday = calculate_sma(serie[:i], long_period, date_yesterday, SMA_200_MISSING_THRESH)

                if any(x is None for x in [ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday]):
                    print(f"[{idx}/{total}] {slug}: dati mancanti per {floor_field} (date: {date_today})")
                    continue

                if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
                    floor_native, floor_usd = get_floor_usd_and_native(conn, collection_id, date_today)
                    insert_golden_cross(conn, collection_id, chain, date_today, is_native,
                                        floor_native, floor_usd,
                                        ma_short_today, ma_long_today,
                                        ma_short_yesterday, ma_long_yesterday,
                                        short_period, long_period)
                    crosses_found += 1
                    print(f"[{idx}/{total}] {slug} - Golden Cross rilevata/registrata in data {date_today} ({'native' if is_native else 'usd'})")

            print(f"[{idx}/{total}] {slug} - Golden Cross trovate nella serie ({floor_field}): {crosses_found}")
            gc_total += crosses_found
    print(f"\nTotale Golden Cross storiche individuate: {gc_total}")
    conn.commit()

# ======= FUNZIONE 2: Golden Cross solo per OGGI =======
def detect_current_golden_crosses(conn):
    """
    Controlla SOLO l’ultima data disponibile per ogni collezione: registra una Golden Cross solo se si è verificata oggi.
    """
    collections = get_collections(conn)
    total = len(collections)
    gc_total = 0

    for idx, (collection_id, slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")

        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, collection_id, floor_field)
            short_period = MA_SHORT
            long_period = MA_LONG

            if len(serie) < long_period + 1:
                print(f"[{idx}/{total}] {slug}: dati insufficienti per la media mobile ({floor_field})")
                continue

            date_list = [d for d, v in serie]
            i = len(date_list) - 1  # SOLO ultimo giorno utile (oggi o ultima data disponibile)
            date_today = date_list[i]
            date_yesterday = date_list[i-1]

            ma_short_today = calculate_sma(serie[:i+1], short_period, date_today, SMA_50_MISSING_THRESH)
            ma_long_today = calculate_sma(serie[:i+1], long_period, date_today, SMA_200_MISSING_THRESH)
            ma_short_yesterday = calculate_sma(serie[:i], short_period, date_yesterday, SMA_50_MISSING_THRESH)
            ma_long_yesterday = calculate_sma(serie[:i], long_period, date_yesterday, SMA_200_MISSING_THRESH)

            if any(x is None for x in [ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday]):
                print(f"[{idx}/{total}] {slug}: dati mancanti per {floor_field} ({date_today})")
                continue

            if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
                floor_native, floor_usd = get_floor_usd_and_native(conn, collection_id, date_today)
                insert_golden_cross(conn, collection_id, chain, date_today, is_native,
                                    floor_native, floor_usd,
                                    ma_short_today, ma_long_today,
                                    ma_short_yesterday, ma_long_yesterday,
                                    short_period, long_period)
                gc_total += 1
                print(f"[{idx}/{total}] {slug} - Golden Cross ODIERNA registrata ({'native' if is_native else 'usd'}) in data {date_today}")

    print(f"\nTotale Golden Cross attuali individuate: {gc_total}")
    conn.commit()