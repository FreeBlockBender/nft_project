import os
import sqlite3
from app.config.config import load_config
from app.config.logging_config import setup_logging
import logging

def table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
        (table_name,)
    )
    return cur.fetchone() is not None

def get_record_count(conn, table_name):
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]
    except sqlite3.Error:
        return "N/A"

def main():
    setup_logging()
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    tables_to_check = [
        "historical_nft_data",
        "nft_collections",
        "historical_golden_crosses"
    ]

    logging.info(f"\nDatabase target: {db_path}")

    # Controllo esistenza file database
    if not os.path.exists(db_path):
        logging.info("Il file del database NON esiste.")
        return
    else:
        logging.info("Il file del database esiste.")

    # Connessione e controllo tabelle
    conn = sqlite3.connect(db_path)
    for table in tables_to_check:
        logging.info(f"\nControllo tabella '{table}':")
        if table_exists(conn, table):
            count = get_record_count(conn, table)
            logging.info(f"Tabella trovata. Numero record: {count}")
        else:
            logging.info(f"Tabella NON trovata.")
    conn.close()

if __name__ == "__main__":
    main()