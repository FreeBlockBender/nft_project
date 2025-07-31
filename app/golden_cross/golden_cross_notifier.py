import sqlite3
from datetime import datetime, timedelta
from app.telegram.utils.telegram_notifier import send_telegram_message, get_gc_draft_chat_id
from app.telegram.utils.telegram_msg_templates import format_golden_cross_msg
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

def notify_monthly_crosses(conn, days=30, ma_short_period=None, ma_long_period=None):
    """
    Notifica tutte le Golden Cross degli ultimi 'days' (default=30 giorni).
    Filtri opzionali su ma_short_period e ma_long_period.
    """
    today = datetime.utcnow().date()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    crosses = get_crosses_between_dates(
        conn, from_date, to_date, ma_short_period=ma_short_period, ma_long_period=ma_long_period
    )
    notify_crosses(conn, crosses, label=f"ultimo periodo ({from_date} - {to_date})")