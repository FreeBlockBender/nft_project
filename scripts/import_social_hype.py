"""
Script: import_social_hype.py
Importa il social hype del mercato NFT usando l'API di Grok.
Eseguire: python scripts/import_social_hype.py
"""

from app.config.logging_config import setup_logging
from app.data_import.import_social_hype import import_nft_social_hype
import logging


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Script: import_social_hype.py")
    logger.info("="*50)
    import_nft_social_hype()
    logger.info("="*50)
    logger.info("Operazione completata.")


if __name__ == "__main__":
    main()
