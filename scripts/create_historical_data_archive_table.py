"""
Script per la creazione della tabella di archivio storica NFT dati.

Crea la tabella 'historical_nft_data_archive' identica alla tabella principale,
se non esiste.
"""

import sqlite3
from app.config.config import load_config
from app.config.logging_config import setup_logging
import logging

def create_archive_table():
    setup_logging()
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Copia la definizione da historical_nft_data, modificando SOLO il nome tabella.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_nft_data_archive (
        collection_identifier TEXT,
        contract_address TEXT,
        slug TEXT,
        latest_floor_date TEXT,
        latest_floor_timestamp TEXT,
        floor_native REAL,
        floor_usd REAL,
        chain TEXT,
        chain_currency_symbol TEXT,
        marketplace_source TEXT,
        ranking INTEGER,
        unique_owners INTEGER,
        total_supply INTEGER,
        listed_count INTEGER,
        best_price_url TEXT,
        sale_count_24h INTEGER,
        sale_volume_native_24h REAL,
        highest_sale_native_24h REAL,
        lowest_sale_native_24h REAL,
        PRIMARY KEY (collection_identifier, chain, latest_floor_date)
    );
    """)
    logging.info("Tabella historical_nft_data_archive creata o già esistente.")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_archive_table()