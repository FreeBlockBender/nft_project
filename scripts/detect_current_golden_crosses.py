# Script di lancio per individuare SOLO le Golden Cross attuali (“di oggi”)

from app.utils.golden_cross_calculator import detect_current_golden_crosses
from app.config import load_config
import sqlite3

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    detect_current_golden_crosses(conn)
    conn.close()

if __name__ == "__main__":
    main()