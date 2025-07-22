# Script che notifica le Golden Cross per TUTTE le date trovate nella tabella (non solo oggi!)

from app.utils.golden_cross_notifier import notify_historical_crosses
from app.config import load_config
import sqlite3

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Per accedere alle colonne come dict
    notify_historical_crosses(conn)
    conn.close()

if __name__ == "__main__":
    main()