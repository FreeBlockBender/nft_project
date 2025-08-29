from app.config.logging_config import setup_logging
from app.data_import.import_csv import import_csv_folder
import logging

def main():
    setup_logging()
    #logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    logging.info("Avvio import CSV NFT dati storici...")
    import_csv_folder()
    logging.info("Import completato.")

if __name__ == "__main__":
    main()