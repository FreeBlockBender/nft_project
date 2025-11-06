import asyncio
import sqlite3
import argparse
from app.config.config import load_config
from app.golden_cross.golden_cross_notifier import notify_monthly_crosses

def main():
    parser = argparse.ArgumentParser(description="Notifica le Golden Cross mensili con filtri opzionali sulle medie mobili.")
    parser.add_argument(
        "--ma-set",
        type=str,
        default="none",
        choices=["none", "20-50", "50-200"],
        help="Filtra per periodi. Valori possibili: none (default), 20-50, 50-200."
    )
    args = parser.parse_args()

    # Decodifica i parametri ma_short/ma_long
    ma_short, ma_long = None, None
    if args.ma_set == "20-50":
        ma_short, ma_long = 20, 50
    elif args.ma_set == "50-200":
        ma_short, ma_long = 50, 200

    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Run the async function properly
        asyncio.run(notify_monthly_crosses(conn, ma_short_period=ma_short, ma_long_period=ma_long))
    finally:
        conn.close()

if __name__ == "__main__":
    main()