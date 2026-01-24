import asyncio
import sqlite3
from datetime import datetime
from app.golden_cross.moving_average import calculate_sma, is_golden_cross
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.telegram.utils.telegram_msg_templates import get_golden_cross_summary_msg

def get_collections(conn):
    """Recupera tutte le collezioni NFT dal DB."""
    cur = conn.cursor()
    cur.execute("SELECT distinct slug, chain FROM nft_collections")
    return cur.fetchall()

def get_floor_series(conn, slug, floor_field):
    """Recupera la serie storica del floor price scelto (nativo/usd)."""
    cur = conn.cursor()
    cur.execute(
        f"SELECT latest_floor_date, {floor_field} FROM historical_nft_data "
        f"WHERE slug = ? AND {floor_field} IS NOT NULL "
        "ORDER BY latest_floor_date ASC",
        (slug,)
    )
    return cur.fetchall()

def get_floor_usd_and_native(conn, slug, date, chain):
    """Recupera floor_native, floor_usd e ranking per collezione, data e CHAIN specifica."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT floor_native, floor_usd, ranking 
        FROM historical_nft_data 
        WHERE slug = ? 
          AND latest_floor_date = ? 
          AND chain = ?
        """,
        ( slug, date, chain)
    )
    return cur.fetchone() or (None, None, None)

def insert_golden_cross(conn, slug, chain, date, is_native,
                        floor_native, floor_usd, ranking,
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
            (slug, chain, date, inserted_ts, is_native, floor_native, floor_usd, ranking,
             ma_short, ma_long, ma_short_previous_day, ma_long_previous_day, ma_short_period, ma_long_period)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (slug, chain, date, datetime.utcnow().isoformat(), int(is_native),
              floor_native, floor_usd, ranking,
              ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday,
              short_period, long_period))
        return True  # Inserimento ok
    except sqlite3.IntegrityError as e:
        print(
            f"[DUPLICATO] Golden Cross già presente: "
            f"slug='{slug}', chain='{chain}', date='{date}', "
            f"ma_short_period={short_period}, ma_long_period={long_period} -- "
            f"Errore: {e}"
        )
        return False  # Duplicato, non inserito
    
def detect_all_historical_golden_crosses(
    conn,
    short_period,
    long_period,
    short_thresh,
    long_thresh,
    start_date: str | None = None   # NUOVO: data di inizio (YYYY-MM-DD), inclusiva
):
    """
    Rileva tutte le Golden Cross storiche, ma **solo a partire da start_date**.
    Se start_date è None, analizza tutto (come prima).
    """
    from datetime import datetime

    collections = get_collections(conn)
    total = len(collections)
    golden_cross_detected = 0
    golden_cross_inserted = 0

    # Converti start_date in oggetto date (se presente)
    start_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Formato data non valido: '{start_date}'. Usa YYYY-MM-DD.")

    for idx, (slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")
        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, slug, floor_field)
            if len(serie) < long_period + 1:
                print(f"[{idx}/{total}] {slug}: dati insufficienti per la media mobile ({floor_field})")
                continue

            date_list = [d for d, v in serie]

            # Trova l'indice minimo da cui partire (rispettando sia i dati per la MA che la data di inizio)
            start_idx = long_period  # necessario per calcolare MA di lungo periodo
            if start_dt:
                # Trova il primo indice con data >= start_date
                for i, d in enumerate(date_list):
                    try:
                        current_dt = datetime.strptime(d, "%Y-%m-%d").date()
                        if current_dt >= start_dt:
                            start_idx = max(start_idx, i)
                            break
                    except ValueError:
                        continue
                else:
                    # Nessuna data >= start_date
                    continue

            # Ciclo solo da start_idx in poi
            for i in range(start_idx, len(date_list)):
                date_today = date_list[i]
                date_yesterday = date_list[i - 1]

                ma_short_today = calculate_sma(serie[:i + 1], short_period, date_today, short_thresh)
                ma_long_today = calculate_sma(serie[:i + 1], long_period, date_today, long_thresh)
                ma_short_yesterday = calculate_sma(serie[:i], short_period, date_yesterday, short_thresh)
                ma_long_yesterday = calculate_sma(serie[:i], long_period, date_yesterday, long_thresh)

                if any(x is None for x in [ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday]):
                    continue

                if is_golden_cross(ma_short_today, ma_long_today, ma_short_yesterday, ma_long_yesterday):
                    floor_native, floor_usd, ranking = get_floor_usd_and_native(conn, slug, date_today, chain)
                    golden_cross_detected += 1
                    inserted = insert_golden_cross(
                        conn, slug, chain, date_today, is_native,
                        floor_native, floor_usd, ranking,
                        ma_short_today, ma_long_today,
                        ma_short_yesterday, ma_long_yesterday,
                        short_period, long_period
                    )
                    if inserted:
                        golden_cross_inserted += 1
                    print(f"[{idx}/{total}] {slug} - Golden Cross in {date_today} ({'native' if is_native else 'usd'})")

    print(f"\nTotale Golden Cross individuate (da {start_date or 'inizio dati'}): {golden_cross_detected}")
    print(f"Record inseriti nel DB: {golden_cross_inserted}")
    conn.commit()

    # Telegram recap
    chat_id = get_monitoring_chat_id()
    msg = get_golden_cross_summary_msg(
        mode='historical',
        ma_short=short_period,
        ma_long=long_period,
        total_crosses=golden_cross_detected,
        inserted_records=golden_cross_inserted,
        start_date=start_date
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
    for idx, (slug, chain) in enumerate(collections, 1):
        print(f"\nCollezione {idx} di {total} – Slug: {slug}")
        for floor_field, is_native in [("floor_native", True), ("floor_usd", False)]:
            serie = get_floor_series(conn, slug, floor_field)
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
                floor_native, floor_usd, ranking = get_floor_usd_and_native(conn, slug, date_today, chain)
                golden_cross_detected += 1
                inserted = insert_golden_cross(conn, slug, chain, date_today, is_native,
                                    floor_native, floor_usd, ranking,
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
        inserted_records=golden_cross_inserted,
        start_date=date_today
    )
    
    asyncio.run(send_telegram_message(msg, chat_id))

    return golden_cross_detected, golden_cross_inserted