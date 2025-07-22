import sqlite3
from datetime import datetime
from app.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.utils.telegram_msg_templates import format_golden_cross_msg
from app.config import load_config

config = load_config()
db_path = config.get("DB_PATH", "nft_data.sqlite3")

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

def notify_crosses_for_date(conn, target_date):
    """
    Funzione generale: Notifica tutte le Golden Cross della data passata come parametro (può essere oggi o un'altra).
    """
    crosses = get_crosses_by_date(conn, target_date)

    if not crosses:
        print(f"Nessuna Golden Cross trovata per la data: {target_date}.")
        return

    print(f"Golden Cross trovate per {target_date}: {len(crosses)}")
    chat_id = get_monitoring_chat_id()
    count_sent = 0

    for cross in crosses:
        nft_data = get_nftdata(conn, cross['collection_identifier'], target_date)
        if nft_data:
            # Prefissi tabella per compatibilità con il template dei messaggi
            msg_data = {}
            for k in cross.keys():
                msg_data[f"historical_golden_crosses.{k}"] = cross[k]
            for k in nft_data.keys():
                msg_data[f"historical_nft_data.{k}"] = nft_data[k]
            msg = format_golden_cross_msg(msg_data)
            send_telegram_message(msg, chat_id)
            count_sent += 1

    print(f"Inviati {count_sent} messaggi Golden Cross su Telegram.")

def notify_today_crosses(conn):
    """Notifica SOLO le Golden Cross della data odierna."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    notify_crosses_for_date(conn, today)

def notify_historical_crosses(conn):
    """
    Notifica tutte le Golden Cross storiche, per TUTTE le date presenti nella tabella.
    Utile solo per invii massivi o test.
    """
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT date FROM historical_golden_crosses ORDER BY date ASC")
    dates = [row[0] for row in cur.fetchall()]
    for d in dates:
        notify_crosses_for_date(conn, d)