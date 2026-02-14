"""
Script: view_social_hype.py
Visualizza gli attuali dati di social hype del mercato NFT.
Eseguire: python scripts/view_social_hype.py
"""

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
import logging
from datetime import datetime


def view_latest_hype():
    """
    Mostra i dati di social hype più recenti dal database.
    """
    logger = logging.getLogger(__name__)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Recupera tutti i record di social hype ordinati per data
        cursor.execute("""
            SELECT date, hype_score, sentiment, trend, keywords, summary, created_at
            FROM nft_social_hype
            ORDER BY date DESC
            LIMIT 10
        """)

        results = cursor.fetchall()
        conn.close()

        if results:
            print("\n" + "="*70)
            print("📊 NFT SOCIAL HYPE - DATI RECENTI")
            print("="*70)
            
            for i, (date, hype_score, sentiment, trend, keywords, summary, created_at) in enumerate(results, 1):
                print(f"\n[{i}] Date: {date}")
                print(f"    Hype Score: {hype_score}/100 {'🚀' if hype_score >= 75 else '📊' if hype_score >= 50 else '❄️'}")
                print(f"    Sentiment: {sentiment}")
                print(f"    Trend: {trend}")
                print(f"    Keywords: {keywords}")
                print(f"    Summary: {summary}")
                print(f"    Updated: {created_at}")
                print("-" * 70)
        else:
            print("\n❌ Nessun dato di social hype trovato nel database.")
            print("   Esegui: python scripts/import_social_hype.py")

    except Exception as e:
        logger.error(f"Errore: {e}")
        print(f"\n❌ Errore: {e}")


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Script: view_social_hype.py")
    logger.info("="*50)
    view_latest_hype()
    logger.info("="*50)


if __name__ == "__main__":
    main()
