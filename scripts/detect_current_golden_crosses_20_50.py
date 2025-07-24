import sqlite3
from app.config import load_config
from app.utils.golden_cross_calculator import detect_current_golden_crosses

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)

    # Parametri per 20-50
    short = int(config["SMA_20"])
    long = int(config["SMA_50"])
    short_thresh = int(config["SMA_20_MISSING_THRESH"])
    long_thresh = int(config["SMA_50_MISSING_THRESH"])

    detect_current_golden_crosses(conn, short, long, short_thresh, long_thresh)
    conn.close()

if __name__ == "__main__":
    main()