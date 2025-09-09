import sqlite3
import asyncio
import logging
from app.config.config import load_config
from app.golden_cross.golden_cross_notifier import notify_today_crosses

# Configure logging
logging.basicConfig(
    filename='golden_cross.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def main():
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        logging.info("Starting Golden Cross notification for today")
        asyncio.run(notify_today_crosses(conn))
        logging.info("Notification process completed")
    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()