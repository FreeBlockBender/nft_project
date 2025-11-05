# scripts/detect_historical_golden_crosses_20_50.py
import sys
import sqlite3
from app.config.config import load_config
from app.golden_cross.golden_cross_calculator import detect_all_historical_golden_crosses

def main():
    # --------------------------------------------------------------
    # 1. Leggi la data da CLI (opzionale)
    # --------------------------------------------------------------
    start_date = None
    if len(sys.argv) > 1:
        raw_date = sys.argv[1].strip()
        try:
            # Valida formato YYYY-MM-DD
            from datetime import datetime
            datetime.strptime(raw_date, "%Y-%m-%d")
            start_date = raw_date
            print(f"Avvio rilevamento Golden Cross a partire da: {start_date}")
        except ValueError:
            print(f"Formato data non valido: '{raw_date}'. Usa YYYY-MM-DD.")
            sys.exit(1)
    else:
        print("Nessuna data specificata → analisi su TUTTA la storia")

    # --------------------------------------------------------------
    # 2. Carica config e DB
    # --------------------------------------------------------------
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)

    short = int(config["SMA_50"])
    long_ = int(config["SMA_200"])
    short_thresh = int(config["SMA_50_MISSING_THRESH"])
    long_thresh = int(config["SMA_200_MISSING_THRESH"])

    # --------------------------------------------------------------
    # 3. Esegui rilevamento con filtro data
    # --------------------------------------------------------------
    detected, inserted = detect_all_historical_golden_crosses(
        conn,
        short_period=short,
        long_period=long_,
        short_thresh=short_thresh,
        long_thresh=long_thresh,
        start_date=start_date  # ← ORA PASSATO!
    )

    print(f"\nRilevazione completata.")
    print(f"Golden Cross trovate: {detected}")
    print(f"Record inseriti: {inserted}")

    conn.close()

if __name__ == "__main__":
    main()