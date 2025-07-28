from app.config.logging_config import setup_logging
from app.database.database import create_tables_if_not_exist
import logging

def main():
    setup_logging()
    #logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    logging.info("Avvio creazione tabelle database NFT...")
    create_tables_if_not_exist(logging)
    logging.info("Processo completato.")

if __name__ == "__main__":
    main()