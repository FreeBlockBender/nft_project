import sqlite3
from datetime import datetime, timedelta
from app.telegram.utils.telegram_notifier import send_telegram_message, get_gc_draft_chat_id
from app.telegram.utils.telegram_msg_templates import (
    format_golden_cross_msg,
    format_golden_cross_monthly_recap_msg
)
from app.config.config import load_config

config = load_config()
db_path = config.get("DB_PATH", "nft_data.sqlite3")

def get_crosses_between_dates(conn, date_from, date_to, ma_short_period=None, ma_long_period=None):
    """Recupera tutte le Golden Cross tra due date (inclusive), con filtri opzionali sulle medie."""
    cur = conn.cursor()
    # Costruisci dinamicamente la query SQL ed i parametri
    query = """
        SELECT * FROM historical_golden_crosses
        WHERE date BETWEEN ? AND ?
    """
    params = [date_from, date_to]
    if ma_short_period is not None and ma_long_period is not None:
        query += " AND ma_short_period = ? AND ma_long_period = ?"
        params.extend([ma_short_period, ma_long_period])
    query += " ORDER BY date DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()


def get_crosses_by_date(conn, target_date):
    """Recupera tutti i Golden Cross della data specificata."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM historical_golden_crosses
        WHERE date = ?
    """, (target_date,))
    return cur.fetchall()

def get_nftdata(conn, collection_identifier, target_date):
    """Recupera dati dalla tabella historical_nft_data per una specifica data."""
    cur = conn.cursor()
    cur.execute("""
        SELECT slug, ranking, floor_native, floor_usd,
               contract_address, chain, chain_currency_symbol,
               unique_owners, total_supply, listed_count, best_price_url
        FROM historical_nft_data
        WHERE collection_identifier = ? AND latest_floor_date = ?
        LIMIT 1
    """, (collection_identifier, target_date))
    return cur.fetchone()

def notify_crosses(conn, crosses, label="periodo selezionato"):
    """Invia su Telegram tutte le Golden Cross passate come lista 'crosses'."""
    if not crosses:
        print(f"Nessuna Golden Cross trovata per il {label}.")
        return
    print(f"Golden Cross trovate per {label}: {len(crosses)}")
    chat_id = get_gc_draft_chat_id()
    count_sent = 0
    for cross in crosses:
        # Le colonne sono accessibili sia come dict (sqlite Row) che posizionamento.
        nft_data = get_nftdata(conn, cross['collection_identifier'], cross['date'])
        if nft_data:
            # Costruisce dizionario unificato (come prima)
            msg_data = {}
            for k in cross.keys():
                msg_data[f"historical_golden_crosses.{k}"] = cross[k]
                msg_data[k] = cross[k]
            for idx, k in enumerate(nft_data.keys()):
                msg_data[f"historical_nft_data.{k}"] = nft_data[k]
                msg_data[k] = nft_data[k]
            msg = format_golden_cross_msg(msg_data)
            send_telegram_message(msg, chat_id)
            count_sent += 1
    print(f"Inviati {count_sent} messaggi Golden Cross su Telegram ({label}).")

def notify_today_crosses(conn):
    """Notifica SOLO le Golden Cross della data odierna."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    crosses = get_crosses_by_date(conn, today)
    notify_crosses(conn, crosses, label="data odierna")

def notify_monthly_crosses(conn, days=365, ma_short_period=None, ma_long_period=None):
    """
    Invia un solo messaggio di recap con TUTTE le Golden Cross trovate nell'ultimo mese, secondo la formattazione specifica.
    """
    today = datetime.utcnow().date()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    crosses = get_crosses_between_dates(
        conn, from_date, to_date, ma_short_period=ma_short_period, ma_long_period=ma_long_period
    )

    unified_data = []
    # Prepara una sola lista di dict, ciascuno con i dati aggregati richiesti per ogni cross
    for cross in crosses:
        # Dati della cross nel giorno
        collection_identifier = cross["collection_identifier"]
        cross_date = cross["date"]
        is_native = cross["is_native"]
        # Dati NFT nel giorno della GC
        nft_row = get_nftdata(conn, collection_identifier, cross_date)
        if not nft_row:
            continue
        # Dati attuali della collezione (record più recente di historical_nft_data)
        cur = conn.cursor()
        cur.execute(
            "SELECT floor_native, floor_usd, chain_currency_symbol, latest_floor_date "
            "FROM historical_nft_data WHERE collection_identifier = ? ORDER BY latest_floor_date DESC LIMIT 1",
            (collection_identifier,)
        )
        current_nft_row = cur.fetchone()
        if not current_nft_row:
            continue

        item = {}
        item["slug"] = nft_row["slug"]
        item["chain"] = nft_row["chain"]
        item["is_native"] = is_native
        item["chain_currency_symbol"] = nft_row["chain_currency_symbol"]
        item["floor_native"] = cross["floor_native"]
        item["floor_usd"] = cross["floor_usd"]
        item["date"] = cross_date
        item["current_floor_native"] = current_nft_row["floor_native"]
        item["current_floor_usd"] = current_nft_row["floor_usd"]
        unified_data.append(item)

    today_str = today.strftime("%d-%m-%Y")
    ma1 = ma_short_period if ma_short_period is not None else "?"
    ma2 = ma_long_period if ma_long_period is not None else "?"

    msg = format_golden_cross_monthly_recap_msg(unified_data, ma1, ma2, today_str)
    chat_id = get_gc_draft_chat_id()
    send_telegram_message(msg, chat_id)