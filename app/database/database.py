
import os
import sqlite3
from app.config.config import load_config

def create_tables_if_not_exist(logger=None):
    """
    Crea il database (se non esiste) e le tre tabelle richieste.
    La funzione è idempotente: esegue CREATE TABLE IF NOT EXISTS per evitare errori.
    Il percorso del database viene letto dalla configurazione (.env).
    """
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Tabella: historical_nft_data
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_nft_data (
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
    if logger:
        logger.info("Tabella historical_nft_data creata.")

    # Indice: idx_collection_date sulla tabella historical_nft_data
    # Nota: l'indice usa le colonne collection_identifier e date.
    # Basandosi sullo schema fornito, useremo latest_floor_date al posto di date
    # per l'indicizzazione basata sulla data della quotazione.
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_collection_date ON historical_nft_data (collection_identifier, latest_floor_date);
    """)
    if logger:
        logger.info("Indice idx_collection_date creato sulla tabella historical_nft_data.")


    # Tabella: nft_collections
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nft_collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        collection_identifier TEXT,
        contract_address TEXT,
        slug TEXT,
        name TEXT,
        chain TEXT,
        chain_currency_symbol TEXT,
        categories TEXT
    );
    """)
    if logger:
        logger.info("Tabella nft_collections creata.")

    # Tabella: historical_golden_crosses
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historical_golden_crosses (
        collection_identifier TEXT,
        chain TEXT,
        date TEXT,
        inserted_ts TEXT,
        is_native INTEGER,
        floor_native REAL,
        floor_usd REAL,
        ranking INTEGER,
        ma_short REAL,
        ma_long REAL,
        ma_short_previous_day REAL,
	    ma_long_previous_day REAL,
        ma_short_period INTEGER,
        ma_long_period INTEGER,
        PRIMARY KEY (date, collection_identifier, chain, ma_short_period, ma_long_period)
    );
    """)
    if logger:
        logger.info("Tabella historical_golden_crosses creata.")

    # Tabella: nft_social_hype
    # Misura il sentiment e l'hype del mercato NFT generale usando l'API di Grok
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nft_social_hype (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        timestamp TEXT,
        hype_score INTEGER,
        sentiment TEXT,
        trend TEXT,
        keywords TEXT,
        summary TEXT,
        raw_response TEXT,
        created_at TEXT,
        UNIQUE(date)
    );
    """)
    if logger:
        logger.info("Tabella nft_social_hype creata.")

    # Indice sulla tabella nft_social_hype
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_social_hype_date ON nft_social_hype (date DESC);
    """)
    if logger:
        logger.info("Indice idx_social_hype_date creato sulla tabella nft_social_hype.")

    conn.commit()
    conn.close()


def get_db_connection():
    """
    Restituisce una connessione attiva al database.
    """
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    conn = sqlite3.connect(db_path)
    return conn

