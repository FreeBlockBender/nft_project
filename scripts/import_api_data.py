from app.utils.logging_config import setup_logging
from app.data_import.import_api import import_nft_collections_via_api
import logging 

def main():
    setup_logging()
    #logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    logging.info("Avvio importazione NFT historical data via API...")
    import_nft_collections_via_api()
    logging.info("Importazione API completata.")

if __name__ == "__main__":
    main()