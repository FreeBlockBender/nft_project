import sqlite3
from app.config.config import load_config
from app.golden_cross.golden_cross_notifier import notify_today_crosses

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    # Attiva Row factory per accesso dict-like
    conn.row_factory = sqlite3.Row

    notify_today_crosses(conn)
    conn.close()

if __name__ == "__main__":
    main()