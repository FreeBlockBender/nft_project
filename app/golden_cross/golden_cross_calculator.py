import sqlite3
from datetime import datetime
from app.golden_cross.moving_average import calculate_sma, is_golden_cross
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.telegram.utils.telegram_msg_templates import get_golden_cross_summary_msg

def get_collections(conn):
    """Recupera tutte le collezioni NFT dal DB."""
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier, slug, chain FROM nft_collections")
    return cur.fetchall()

def get_floor_series(conn, collection_id, floor_field):
    """Recupera la serie storica del floor price scelto (nativo/usd)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT latest_floor_date, {floor_field} FROM historical_nft_data "
        f"WHERE collection_identifier = ? AND {floor_field} IS NOT NULL "
        "ORDER BY latest_floor_date ASC",
        (collection_id,)
    )
    return cur.fetchall()

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
    """
    Inserisce una Golden Cross nella tabella dedicata.
    Restituisce True se l'inserimento ha avuto successo, False se era già presente (IntegrityError).
    """
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO historical_golden_crosses 
            (collection_identifier, chain, date, inserted_ts, is_native, floor_native, floor_usd,
             ma_short, ma_long, ma_short_previous_day, ma_long_previous_day, ma_short_period, ma_long_period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (collection_id, chain, date, datetime.utcnow().isoformat(), int(is_native),
              floor_native, floor_usd,
              ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday,
              short_period, long_period))
        return True  # Inserimento ok
    except sqlite3.IntegrityError as e:
        print(
            f"[DUPLICATO] Golden Cross già presente: "
            f"collection_identifier='{collection_id}', chain='{chain}', date='{date}', "
            f"ma_short_period={short_period}, ma_long_period={long_period} -- "
            f"Errore: {e}"
        )
        return False  # Duplicato, non inserito

def detect_all_historical_golden_crosses(conn, short_period, long_period,
                                         short_thresh, long_thresh):
    """
    Elabora la serie storica di tutte le collezioni per tutte le combinazioni richieste,
    inserisce tutte le Golden Cross che rileva e manda un recap su Telegram.
    """
    collections = get_collections(conn)
    total = len(collections)
    golden_cross_detected = 0  # Numero totale di GC rilevate
    golden_cross_inserted = 0  # Effettivamente inserite in DB
    for idx, (collection_id, slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")
        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, collection_id, floor_field)
            if len(serie) < long_period + 1:
                print(f"[{idx}/{total}] {slug}: dati insufficienti per la media mobile ({floor_field})")
                continue
            date_list = [d for d, v in serie]
            for i in range(long_period, len(date_list)):
                date_today = date_list[i]
                date_yesterday = date_list[i - 1]
                ma_short_today = calculate_sma(serie[:i + 1], short_period, date_today, short_thresh)
                ma_long_today = calculate_sma(serie[:i + 1], long_period, date_today, long_thresh)
                ma_short_yesterday = calculate_sma(serie[:i], short_period, date_yesterday, short_thresh)
                ma_long_yesterday = calculate_sma(serie[:i], long_period, date_yesterday, long_thresh)
                if any(x is None for x in [ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday]):
                    print(f"[{idx}/{total}] {slug}: dati mancanti per {floor_field} (date: {date_today})")
                    continue
                if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
                    floor_native, floor_usd = get_floor_usd_and_native(conn, collection_id, date_today)
                    golden_cross_detected += 1
                    inserted = insert_golden_cross(conn, collection_id, chain, date_today, is_native,
                                        floor_native, floor_usd,
                                        ma_short_today, ma_long_today,
                                        ma_short_yesterday, ma_long_yesterday,
                                        short_period, long_period)
                    if inserted:
                        golden_cross_inserted += 1
                    print(f"[{idx}/{total}] {slug} - Golden Cross rilevata/registrata in data {date_today} ({'native' if is_native else 'usd'})")
    print(f"\nTotale Golden Cross storiche individuate: {golden_cross_detected}")
    print(f"Record inseriti nel DB: {golden_cross_inserted}")
    conn.commit()
    # --- Messaggio Telegram riepilogo ---
    chat_id = get_monitoring_chat_id()
    msg = get_golden_cross_summary_msg(
        mode='historical',
        ma_short=short_period,
        ma_long=long_period,
        total_crosses=golden_cross_detected,
        inserted_records=golden_cross_inserted
    )
    send_telegram_message(msg, chat_id)
    return golden_cross_detected, golden_cross_inserted

def detect_current_golden_crosses(conn, short_period, long_period,
                                  short_thresh, long_thresh):
    """
    Elabora SOLO l’ultima data disponibile per ogni collezione.
    Inserisce e notifica recap Telegram a fine corsa.
    """
    collections = get_collections(conn)
    total = len(collections)
    golden_cross_detected = 0
    golden_cross_inserted = 0
    for idx, (collection_id, slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")
        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, collection_id, floor_field)
            if len(serie) < long_period + 1:
                print(f"[{idx}/{total}] {slug}: dati insufficienti per la media mobile ({floor_field})")
                continue
            date_list = [d for d, v in serie]
            i = len(date_list) - 1
            date_today = date_list[i]
            date_yesterday = date_list[i - 1]
            ma_short_today = calculate_sma(serie[:i + 1], short_period, date_today, short_thresh)
            ma_long_today = calculate_sma(serie[:i + 1], long_period, date_today, long_thresh)
            ma_short_yesterday = calculate_sma(serie[:i], short_period, date_yesterday, short_thresh)
            ma_long_yesterday = calculate_sma(serie[:i], long_period, date_yesterday, long_thresh)
            if any(x is None for x in [ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday]):
                print(f"[{idx}/{total}] {slug}: dati mancanti per {floor_field} ({date_today})")
                continue
            if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
                floor_native, floor_usd = get_floor_usd_and_native(conn, collection_id, date_today)
                golden_cross_detected += 1
                inserted = insert_golden_cross(conn, collection_id, chain, date_today, is_native,
                                    floor_native, floor_usd,
                                    ma_short_today, ma_long_today,
                                    ma_short_yesterday, ma_long_yesterday,
                                    short_period, long_period)
                if inserted:
                    golden_cross_inserted += 1
                print(f"[{idx}/{total}] {slug} - Golden Cross ODIERNA registrata ({'native' if is_native else 'usd'}) in data {date_today}")
    print(f"\nTotale Golden Cross attuali individuate: {golden_cross_detected}")
    print(f"Record inseriti nel DB: {golden_cross_inserted}")
    conn.commit()
    # --- Messaggio Telegram riepilogo ---
    chat_id = get_monitoring_chat_id()
    msg = get_golden_cross_summary_msg(
        mode='current',
        ma_short=short_period,
        ma_long=long_period,
        total_crosses=golden_cross_detected,
        inserted_records=golden_cross_inserted
    )
    send_telegram_message(msg, chat_id)
    return golden_cross_detected, golden_cross_inserted