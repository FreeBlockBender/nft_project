# app/utils/telegram_bot_query_utils.py

import os
import sqlite3
from datetime import datetime, timedelta

def get_db_connection():
    db_path = os.getenv("DB_PATH", "nft_data.sqlite3")
    return sqlite3.connect(db_path)

def get_slugs_by_prefix(prefix):
    """
    Restituisce tutti gli slug che iniziano per una certa lettera/prefisso.
    """
    query = "SELECT slug FROM nft_collections WHERE slug LIKE ? ORDER BY slug COLLATE NOCASE"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (f"{prefix}%",))
        return cur.fetchall()

def get_slugs_by_chain(chain):
    """
    Restituisce tutti gli slug associati a una determinata chain.
    """
    query = "SELECT slug FROM nft_collections WHERE LOWER(chain) = ? ORDER BY slug COLLATE NOCASE"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (chain.lower(),))
        return cur.fetchall()

def get_slugs_by_category(category):
    """
    Restituisce tutti gli slug di una categoria (es: art, gaming...).
    """
    query = "SELECT slug FROM nft_collections WHERE LOWER(categories) = ? ORDER BY slug COLLATE NOCASE"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (category.lower(),))
        return cur.fetchall()

def get_collection_meta(slug):
    """
    Restituisce tutte le info meta di una collezione (modifica le colonne secondo il tuo schema).
    """
    query = "SELECT * FROM nft_collections WHERE slug = ?"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (slug,))
        row = cur.fetchone()
        if not row:
            return None
        # Restituisci come dizionario (adatta i nomi colonne se vuoi)
        col_names = [desc[0] for desc in cur.description]
        return dict(zip(col_names, row))

def get_moving_averages(slug, native=True):
    """
    Calcola medie mobili simple short e long su prezzo 'native' o 'usd'.
    """
    price_col = "price_native" if native else "price_usd"
    query = f"""
        SELECT date, {price_col}
        FROM nft_prices
        WHERE slug = ?
        ORDER BY date DESC
        LIMIT 60
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (slug,))
        rows = cur.fetchall()
        if not rows:
            return None
        prices = [row[1] for row in rows if row[1] is not None]
        if len(prices) < 1:
            return None
        short_ma = sum(prices[:7]) / min(7, len(prices))
        long_ma = sum(prices[:30]) / min(30, len(prices))
        return (
            f"Medie Mobili per {slug} ({'native' if native else 'usd'}):\n"
            f"MA(7): {short_ma:.4f}\n"
            f"MA(30): {long_ma:.4f}"
        )

def get_collection_chart_data(slug, days=30, price_mode="native"):
    """
    Ritorna una lista di tuple (date, price) per la collezione e il periodo richiesto.
    """
    price_col = "price_native" if price_mode == "native" else "price_usd"
    since = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
    query = f"""
        SELECT date, {price_col}
        FROM nft_prices
        WHERE slug = ?
            AND date >= ?
        ORDER BY date
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (slug, since))
        return cur.fetchall()

def get_missing_days_report(slug):
    """
    Individua giorni mancanti nel db per lo slug.
    """
    # Supponiamo i dati vadano da start_date a today:
    query = "SELECT MIN(date), MAX(date) FROM nft_prices WHERE slug = ?"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (slug,))
        result = cur.fetchone()
        if not result or not result[0]:
            return "Nessun dato per questa collezione."
        start_date = datetime.strptime(result[0], "%Y-%m-%d").date()
        end_date = datetime.strptime(result[1], "%Y-%m-%d").date()
        # Recupero tutte le date effettivamente presenti:
        cur.execute(
            "SELECT DISTINCT date FROM nft_prices WHERE slug = ? ORDER BY date",
            (slug,),
        )
        existing = {datetime.strptime(row[0], "%Y-%m-%d").date() for row in cur.fetchall()}
        all_days = {start_date + timedelta(days=x) for x in range((end_date-start_date).days+1)}
        missing = sorted(all_days - existing)
        if not missing:
            return "Non risultano giorni mancanti."
        return f"Giorni mancanti per {slug}:\n" + "\n".join([str(d) for d in missing])

def get_daily_insert_report():
    """
    Report per controllo inserimento dati nel giorno corrente.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    query = "SELECT slug FROM nft_prices WHERE date = ?"
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (today,))
        slugs = [row[0] for row in cur.fetchall()]
        if not slugs:
            return "Nessun inserimento oggi."
        return f"Collezioni aggiornate oggi ({today}):\n" + ", ".join(slugs)