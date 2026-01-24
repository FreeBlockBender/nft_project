"""
Script per aggiungere la colonna 'ranking' alla tabella 'historical_golden_crosses'.
Questo script:
1. Aggiunge la colonna 'ranking' alla tabella esistente
2. Popola i valori di ranking recuperandoli dalla tabella historical_nft_data
"""

import sqlite3
import logging
from app.config.config import load_config
from app.config.logging_config import setup_logging

def add_ranking_column(conn):
    """Aggiunge la colonna ranking alla tabella historical_golden_crosses se non esiste."""
    cur = conn.cursor()
    
    # Verifica se la colonna esiste già
    cur.execute("PRAGMA table_info(historical_golden_crosses)")
    columns = [row[1] for row in cur.fetchall()]
    
    if 'ranking' in columns:
        logging.info("La colonna 'ranking' esiste già nella tabella historical_golden_crosses")
        return False
    
    # Aggiunge la colonna
    try:
        cur.execute("ALTER TABLE historical_golden_crosses ADD COLUMN ranking INTEGER")
        conn.commit()
        logging.info("Colonna 'ranking' aggiunta con successo alla tabella historical_golden_crosses")
        return True
    except sqlite3.Error as e:
        logging.error(f"Errore durante l'aggiunta della colonna 'ranking': {e}")
        raise

def populate_ranking_values(conn):
    """Popola i valori di ranking recuperandoli dalla tabella historical_nft_data."""
    cur = conn.cursor()
    
    # Recupera tutti i record di historical_golden_crosses
    cur.execute("""
        SELECT slug, chain, date, ma_short_period, ma_long_period
        FROM historical_golden_crosses
        WHERE ranking IS NULL
    """)
    
    golden_crosses = cur.fetchall()
    total = len(golden_crosses)
    
    if total == 0:
        logging.info("Nessun record da aggiornare (tutti hanno già il ranking o la tabella è vuota)")
        return
    
    logging.info(f"Trovati {total} record da aggiornare con il ranking")
    
    updated = 0
    not_found = 0
    
    for idx, (slug, chain, date, ma_short_period, ma_long_period) in enumerate(golden_crosses, 1):
        # Recupera il ranking dalla tabella historical_nft_data
        cur.execute("""
            SELECT ranking
            FROM historical_nft_data
            WHERE slug = ? AND chain = ? AND latest_floor_date = ?
            LIMIT 1
        """, (slug, chain, date))
        
        result = cur.fetchone()
        
        if result:
            ranking = result[0]
            # Aggiorna il record in historical_golden_crosses
            cur.execute("""
                UPDATE historical_golden_crosses
                SET ranking = ?
                WHERE slug = ? AND chain = ? AND date = ? 
                  AND ma_short_period = ? AND ma_long_period = ?
            """, (ranking, slug, chain, date, ma_short_period, ma_long_period))
            updated += 1
            
            if idx % 100 == 0:
                logging.info(f"Progresso: {idx}/{total} record processati")
                conn.commit()
        else:
            not_found += 1
            logging.warning(f"Ranking non trovato per slug={slug}, chain={chain}, date={date}")
    
    conn.commit()
    
    logging.info(f"Migrazione completata:")
    logging.info(f"  - Record aggiornati: {updated}")
    logging.info(f"  - Record non trovati: {not_found}")

def main():
    setup_logging()
    logging.info("=== Avvio migrazione: aggiunta colonna 'ranking' a historical_golden_crosses ===")
    
    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Step 1: Aggiungi la colonna
        column_added = add_ranking_column(conn)
        
        # Step 2: Popola i valori
        if column_added or True:  # Esegui sempre per sicurezza
            populate_ranking_values(conn)
        
        logging.info("=== Migrazione completata con successo ===")
        
    except Exception as e:
        logging.error(f"Errore durante la migrazione: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
