# app/utils/db_connection.py

import sqlite3
from app.config.config import load_config

config = load_config()
DB_PATH = config.get("DB_PATH", "nft_data.sqlite3")

def get_db_connection():
    """
    Restituisce una connessione SQLite al database NFT.
    Usa il percorso del DB definito in config.py (.env).
    Configura timeout e WAL mode per migliorare l'accesso concorrente.
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    # Enable WAL mode for better concurrent access
    conn.execute("PRAGMA journal_mode=WAL")
    # Increase busy timeout
    conn.execute("PRAGMA busy_timeout=5000")
    return conn