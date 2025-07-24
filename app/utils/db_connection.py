# app/utils/db_connection.py

import sqlite3
from app.config import load_config

config = load_config()
DB_PATH = config.get("DB_PATH", "nft_data.sqlite3")

def get_db_connection():
    """
    Restituisce una connessione SQLite al database NFT.
    Usa il percorso del DB definito in config.py (.env).
    """
    return sqlite3.connect(DB_PATH)