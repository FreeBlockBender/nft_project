import sqlite3
from datetime import datetime, timedelta
from app.config import load_config
from app.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id, get_channel_chat_id
from app.utils.telegram_msg_templates import format_golden_cross_msg

def get_yesterday_str():
    """Restituisce la data di ieri in formato YYYY-MM-DD."""
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

def get_today_crosses(conn):
    # Ricava solo le Golden Cross inserite oggi (campo inserted_ts = oggi in formato YYYY-MM-DD)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("""
        SELECT gc.*, col.slug
        FROM historical_golden_crosses gc
        JOIN nft_collections col ON gc.collection_identifier = col.collection_identifier
        WHERE DATE(gc.inserted_ts) = ?
    """, (today,))
    return cur.fetchall()

def get_nftdata_for_cross_yesterday(conn, collection_identifier):
    """
    Ottiene i dati di dettaglio dalla tabella historical_nft_data,
    filtrando per collection_identifier e latest_floor_date = IERI.
    """
    cur = conn.cursor()
    yesterday = get_yesterday_str()
    cur.execute("""
        SELECT contract_address, chain_currency_symbol, ranking, unique_owners, 
               total_supply, listed_count, best_price_url
        FROM historical_nft_data
        WHERE collection_identifier = ? AND latest_floor_date = ?
        LIMIT 1
    """, (collection_identifier, yesterday))
    return cur.fetchone()

def main():
    config = load_config()
    conn = sqlite3.connect(config["DB_PATH"])
    conn.row_factory = sqlite3.Row  # accedi ai dati come dict
    crosses = get_today_crosses(conn)
    chat_id = get_channel_chat_id()
    count = 0

    for cross in crosses:
        nft_data = get_nftdata_for_cross_yesterday(conn, cross['collection_identifier'])
        if nft_data:
            # Unisci i dati dictionary <-> Row (così funziona il template oggetto.colonna)
            data = dict(cross)
            data.update(dict(nft_data))
            msg = format_golden_cross_msg(data)
            send_telegram_message(msg, chat_id)
            count += 1
    conn.close()
    print(f"Inviati {count} messaggi Golden Cross su Telegram (dati latest_floor_date = ieri).")

if __name__ == "__main__":
    main()