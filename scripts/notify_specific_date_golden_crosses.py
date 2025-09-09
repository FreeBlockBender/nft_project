import asyncio
import sqlite3
import argparse
from datetime import datetime
from app.config.config import load_config
from app.golden_cross.golden_cross_notifier import notify_crosses_for_date

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Notify Golden Crosses for a specific date.")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.utcnow().strftime("%Y-%m-%d"),
        help="Date for Golden Cross notifications (YYYY-MM-DD). Defaults to today."
    )
    args = parser.parse_args()

    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Call async function with specified date
        asyncio.run(notify_crosses_for_date(conn, args.date))
    finally:
        conn.close()

if __name__ == "__main__":
    main()