"""
Script CLI per archiviazione e notifica record storici NFT.
Si limita a chiamare la funzione logica e a gestire il logging/exit code.
"""
import sqlite3
import logging
from app.config.config import load_config
from app.database.archive_logic import archive_and_notify_old_historical_data

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")

    conn = sqlite3.connect(db_path)

    # Esegue la logica completa (archiviazione + notifica)
    outcome = archive_and_notify_old_historical_data(conn)

    conn.close()

    # Log con riepilogo
    logging.basicConfig(level=logging.INFO)
    logging.info(f"{outcome['archived_count']} record archiviati. Data spartiacque: {outcome['cutoff_date']}.")

if __name__ == "__main__":
    main()