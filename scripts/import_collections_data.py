from app.utils.logging_config import setup_logging
from app.data_import.import_collections import import_collections
import logging

def main():
    setup_logging()
    logging.info("Avvio import Metadati NFT collections")
    import_collections()
    logging.info("Import completato")

if __name__ == "__main__":
    main()