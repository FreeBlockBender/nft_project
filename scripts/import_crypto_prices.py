import asyncio
import os
import json
import requests
import logging
import sys
import time
from datetime import datetime
from app.database.database import get_db_connection
from app.utils.helpers import extract_or_none
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.telegram.utils import telegram_msg_templates # Import del modulo per i template

# Configura logging per console e file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('crypto_import.log')
    ]
)

def make_api_request(url, headers=None, params=None, data=None, retries=3, backoff=5):
    """Effettua una richiesta API con retry logic."""
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, params=params, data=data, timeout=60)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                print(f"Retry {attempt + 1}/{retries} after {wait}s due to error: {e}")
                logging.warning(f"Retry {attempt + 1}/{retries} after {wait}s due to error: {e}")
                time.sleep(wait)
            else:
                raise e

def import_crypto_data_via_api():
    """
    Importa dati per la tabella crypto_daily_metrics da CoinGecko.
    chain_gas_fee_gwei è NULL. Salva la risposta API su file.
    Inserisce i record per l'ora corrente.
    """
    print("Starting crypto data import script")
    logging.info("Starting crypto data import script")

    # Configurazione locale
    config = {
        "MOCK_API_MODE": "false",
        "MOCK_API_LOCAL_FILE": "data/local.json"
    }
    mock_mode = str(config.get("MOCK_API_MODE", "false")).lower() == "true"
    print(f"Mock mode: {mock_mode}")
    logging.info(f"Mock mode: {mock_mode}")

    telegram_chat_id = get_monitoring_chat_id()
    print(f"Telegram chat ID: {telegram_chat_id}")
    logging.info(f"Telegram chat ID: {telegram_chat_id}")

    # Genera timestamp per l'ora corrente (YYYY-MM-DD HH:00:00)
    current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    current_hour_str = current_hour.strftime("%Y-%m-%d %H:00:00")
    print(f"Current hour: {current_hour_str}")
    logging.info(f"Current hour: {current_hour_str}")

    data_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data")
    print(f"Data directory: {data_dir}")
    logging.info(f"Data directory: {data_dir}")
    os.makedirs(data_dir, exist_ok=True)

    # File paths
    mock_filename = f"crypto_data_{current_hour.strftime('%Y%m%d_%H')}.json"
    mock_filepath = os.path.join(data_dir, mock_filename)
    fixed_mock_file_path = os.path.join(data_dir, "local.json")
    print(f"Mock file: {fixed_mock_file_path}, Output file: {mock_filepath}")
    logging.info(f"Mock file: {fixed_mock_file_path}, Output file: {mock_filepath}")

    # Configurazione API
    api_configs = {
        "coingecko": {"url": "https://api.coingecko.com/api/v3", "key": None}
    }
    print("API configurations loaded")
    logging.info("API configurations loaded")

    # Inizializzazione contatori per il riepilogo
    crypto_data = []
    inserted_count = 0
    skipped_date_mismatch = 0
    failed_count = 0
    file_save_status = "skipped"

    # --- 1. Caricamento dati (Mock Mode vs API Reale) ---
    if mock_mode:
        print(f"Loading mock data from {fixed_mock_file_path}")
        logging.info(f"Loading mock data from {fixed_mock_file_path}")
        if os.path.exists(fixed_mock_file_path):
            try:
                with open(fixed_mock_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                crypto_data = data.get("coingecko", [])
                print(f"Loaded {len(crypto_data)} items from mock file")
                logging.info(f"Loaded {len(crypto_data)} items from mock file")
            except json.JSONDecodeError as e:
                msg = f"Errore parsing JSON nel file mock {fixed_mock_file_path}: {e}"
                print(msg)
                logging.error(msg)
                asyncio.run(send_telegram_message(msg, telegram_chat_id))
                return
            except Exception as e:
                msg = f"Errore generico caricamento file mock {fixed_mock_file_path}: {e}"
                print(msg)
                logging.error(msg)
                asyncio.run(send_telegram_message(msg, telegram_chat_id))
                return
        else:
            msg = f"Mock file non trovato: {fixed_mock_file_path}. Disabling mock mode and exiting."
            print(msg)
            logging.warning(msg)
            asyncio.run(send_telegram_message(msg, telegram_chat_id))
            return
    else:
        print("Making real API calls")
        logging.info("Making real API calls")
        try:
            # CoinGecko: Prezzi e metriche
            print("Fetching prices and metrics from CoinGecko")
            cg_response = make_api_request(
                f"{api_configs['coingecko']['url']}/coins/markets?vs_currency=usd&ids=bitcoin,ethereum,solana,binancecoin,apecoin,arbitrum,optimism,matic-network,blast"
            )
            cg_data = cg_response.json()
            print("CoinGecko response received")
            logging.info("CoinGecko response received")
            if not isinstance(cg_data, list):
                msg = f"Unexpected CoinGecko response format: {json.dumps(cg_data, indent=2)}"
                print(msg)
                logging.error(msg)
                asyncio.run(send_telegram_message(msg, telegram_chat_id))
                return
            expected_coins = {"bitcoin", "ethereum", "solana", "binancecoin", "apecoin", "arbitrum", "optimism", "matic-network", "blast"}
            received_coins = {coin["id"] for coin in cg_data}
            missing_coins = expected_coins - received_coins
            if missing_coins:
                msg = f"Missing coins in CoinGecko response: {missing_coins}"
                print(msg)
                logging.warning(msg)
                asyncio.run(send_telegram_message(msg, telegram_chat_id))

            for coin in cg_data:
                roi = coin.get("roi", {})
                crypto_data.append({
                    "id": coin.get("id"),
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name"),
                    "image": coin.get("image"),
                    "current_price": coin.get("current_price"),
                    "market_cap": coin.get("market_cap"),
                    "market_cap_rank": coin.get("market_cap_rank"),
                    "fully_diluted_valuation": coin.get("fully_diluted_valuation"),
                    "total_volume": coin.get("total_volume"),
                    "high_24h": coin.get("high_24h"),
                    "low_24h": coin.get("low_24h"),
                    "price_change_24h": coin.get("price_change_24h"),
                    "price_change_percentage_24h": coin.get("price_change_percentage_24h"),
                    "market_cap_change_24h": coin.get("market_cap_change_24h"),
                    "market_cap_change_percentage_24h": coin.get("market_cap_change_percentage_24h"),
                    "circulating_supply": coin.get("circulating_supply"),
                    "total_supply": coin.get("total_supply"),
                    "max_supply": coin.get("max_supply"),
                    "ath": coin.get("ath"),
                    "ath_change_percentage": coin.get("ath_change_percentage"),
                    "ath_date": coin.get("ath_date"),
                    "atl": coin.get("atl"),
                    "atl_change_percentage": coin.get("atl_change_percentage"),
                    "atl_date": coin.get("atl_date"),
                    "roi_times": roi.get("times") if roi else None,
                    "roi_currency": roi.get("currency") if roi else None,
                    "roi_percentage": roi.get("percentage") if roi else None,
                    "last_updated": coin.get("last_updated")
                })
            print(f"Prepared {len(crypto_data)} data items")
            logging.info(f"Prepared {len(crypto_data)} data items")

            # Salva risposta API
            api_data = {
                "coingecko": cg_data
            }
            try:
                with open(mock_filepath, "w", encoding="utf-8") as f:
                    json.dump(api_data, f, ensure_ascii=False, indent=2)
                file_save_status = "success"
                print(f"Saved API response to {mock_filepath}")
                logging.info(f"Saved API response to {mock_filepath}")
            except Exception as e:
                file_save_status = f"error:{str(e)}"
                print(f"Error saving API response: {e}")
                logging.error(f"Error saving API response: {e}")

        except requests.exceptions.RequestException as e:
            msg = f"Errore chiamata API: {e}"
            print(msg)
            logging.error(msg)
            asyncio.run(send_telegram_message(msg, telegram_chat_id))
            return
        except Exception as e:
            msg = f"Eccezione imprevista durante chiamata API: {e}"
            print(msg)
            logging.error(msg)
            asyncio.run(send_telegram_message(msg, telegram_chat_id))
            return

    # --- 2. Validazione e preparazione dati ---
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print("Connected to SQLite database")
        logging.info("Connected to SQLite database")
    except Exception as e:
        msg = f"Errore connessione al database: {e}"
        print(msg)
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        return

    # Query di inserimento
    insert_sql = """
        INSERT OR IGNORE INTO crypto_daily_metrics (
            date, crypto_symbol, id, name, image, current_price, market_cap, market_cap_rank,
            fully_diluted_valuation, total_volume, high_24h, low_24h, price_change_24h,
            price_change_percentage_24h, market_cap_change_24h, market_cap_change_percentage_24h,
            circulating_supply, total_supply, max_supply, ath, ath_change_percentage, ath_date,
            atl, atl_change_percentage, atl_date, roi_times, roi_currency, roi_percentage,
            last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # --- 3. Elaborazione e inserimento dati ---
    total_elements = len(crypto_data)
    print(f"Processing {total_elements} items for database insertion")
    logging.info(f"Processing {total_elements} items for database insertion")

    for item in crypto_data:
        symbol = item.get("symbol", "N/A")
        try:
            values = (
                current_hour_str,
                symbol,
                item.get("id"),
                item.get("name"),
                item.get("image"),
                item.get("current_price"),
                item.get("market_cap"),
                item.get("market_cap_rank"),
                item.get("fully_diluted_valuation"),
                item.get("total_volume"),
                item.get("high_24h"),
                item.get("low_24h"),
                item.get("price_change_24h"),
                item.get("price_change_percentage_24h"),
                item.get("market_cap_change_24h"),
                item.get("market_cap_change_percentage_24h"),
                item.get("circulating_supply"),
                item.get("total_supply"),
                item.get("max_supply"),
                item.get("ath"),
                item.get("ath_change_percentage"),
                item.get("ath_date"),
                item.get("atl"),
                item.get("atl_change_percentage"),
                item.get("atl_date"),
                item.get("roi_times"),
                item.get("roi_currency"),
                item.get("roi_percentage"),
                item.get("last_updated")
            )
            cur.execute(insert_sql, values)
            if cur.rowcount == 1:
                inserted_count += 1
                conn.commit()
                print(f"Inserted record for crypto_symbol '{symbol}' at {current_hour_str}")
                logging.info(f"Inserted record for crypto_symbol '{symbol}' at {current_hour_str}")
            else:
                skipped_date_mismatch += 1
                print(f"Record for crypto_symbol '{symbol}' at {current_hour_str} ignored (duplicate PK)")
                logging.info(f"Record for crypto_symbol '{symbol}' at {current_hour_str} ignored (duplicate PK)")
        except Exception as e:
            failed_count += 1
            conn.rollback()
            print(f"Error processing/inserting crypto_symbol '{symbol}' at {current_hour_str}: {e}")
            logging.error(f"Error processing/inserting crypto_symbol '{symbol}' at {current_hour_str}: {e}")

    conn.close()
    print("Closed database connection")
    logging.info("Closed database connection")

    # --- 4. Messaggio Telegram finale ---
    try:
        summary_msg = telegram_msg_templates.get_crypto_import_summary(
            total_elements=total_elements,
            inserted_count=inserted_count,
            skipped_date_mismatch=skipped_date_mismatch,
            failed_count=failed_count,
            file_save_status=file_save_status
        )
        print(f"Summary: {summary_msg}")
        if telegram_chat_id:
            asyncio.run(send_telegram_message(summary_msg, telegram_chat_id))
        else:
            print("No Telegram chat ID configured")
            logging.warning("No Telegram chat ID configured")
    except Exception as e:
        msg = f"Error generating summary message: {e}"
        print(msg)
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        summary_msg = f"Processed: {total_elements}, Inserted: {inserted_count}, Skipped: {skipped_date_mismatch}, Errors: {failed_count}, Status: {file_save_status}"

    print("Crypto data import completed")
    logging.info("Crypto data import completed")

if __name__ == "__main__":
    try:
        import_crypto_data_via_api()
    except Exception as e:
        print(f"Unexpected error in script: {e}")
        logging.error(f"Unexpected error in script: {e}")