"""
Logica di archiviazione e notifica dei record storici NFT.
"""

import sqlite3
from datetime import datetime, timedelta
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id

ARCHIVE_DAYS = 365  # Valore costante per il cutoff di archiviazione

def archive_and_notify_old_historical_data(conn):
    """
    Sposta i record più vecchi di ARCHIVE_DAYS da 'historical_nft_data'
    a 'historical_nft_data_archive', committa, genera e invia la notifica Telegram
    e restituisce un dizionario con i dati di outcome.
    """
    # Calcola la data spartiacque
    cutoff_date = (datetime.utcnow() - timedelta(days=ARCHIVE_DAYS)).date().isoformat()
    cur = conn.cursor()

    # Seleziona i record da archiviare
    cur.execute("""
        SELECT * FROM historical_nft_data
        WHERE latest_floor_date < ?
    """, (cutoff_date,))
    records = cur.fetchall()
    n_archived = len(records)

    if n_archived:
        # Inserimento nell'archivio
        cur.executemany("""
            INSERT OR IGNORE INTO historical_nft_data_archive
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        # Cancellazione dalla tabella principale
        cur.execute("""
            DELETE FROM historical_nft_data
            WHERE latest_floor_date < ?
        """, (cutoff_date,))
        conn.commit()

    # Generazione messaggio Telegram
    message = (
        f"Archiviazione completata!\n"
        f"Record archiviati: {n_archived}\n"
        f"Data spartiacque: {cutoff_date}"
    )

    # Invio notifica Telegram tramite funzione legacy preesistente
    chat_id = get_monitoring_chat_id()
    send_telegram_message(message, chat_id)

    # Restituisce i dati per log eventuale e testing
    return {
        "archived_count": n_archived,
        "cutoff_date": cutoff_date,
        "notified": True
    }