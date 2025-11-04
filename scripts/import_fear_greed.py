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
        logging.FileHandler('fear_greed_import.log')
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

def import_fear_greed_data():
    """
    Importa il Fear and Greed Index da CoinMarketCap e lo salva nella tabella fear_greed_daily.
    Salva la risposta API su file. Inserisce un record per l'ora corrente.
    """
    print("Starting Fear and Greed Index import script")
    logging.info("Starting Fear and Greed Index import script")

    # Configurazione locale
    config = {
        "MOCK_API_MODE": "false",
        "MOCK_API_LOCAL_FILE": "data/fear_greed_local.json",
        "CMC_API_KEY": "a3655466-9dcd-49e6-86ea-7b40a5c745c4"
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
    mock_filename = f"fear_greed_data_{current_hour.strftime('%Y%m%d_%H')}.json"
    mock_filepath = os.path.join(data_dir, mock_filename)
    fixed_mock_file_path = os.path.join(data_dir, "fear_greed_local.json")
    print(f"Mock file: {fixed_mock_file_path}, Output file: {mock_filepath}")
    logging.info(f"Mock file: {fixed_mock_file_path}, Output file: {mock_filepath}")

    # Configurazione API
    api_configs = {
        "coinmarketcap": {"url": "https://pro-api.coinmarketcap.com", "key": config.get("CMC_API_KEY")}
    }
    print("API configurations loaded")
    logging.info("API configurations loaded")

    # Inizializzazione contatori per il riepilogo
    fear_greed_data = {}
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
                logging.info(f"Mock data loaded: {json.dumps(data, indent=2)}")
                try:
                    fear_greed_data = {
                        "value": data["data"][0]["value"],
                        "value_classification": data["data"][0]["value_classification"],
                        "timestamp": data["data"][0]["timestamp"]
                    }
                except (KeyError, IndexError) as e:
                    logging.warning(f"Direct access failed in mock mode: {e}. Falling back to extract_or_none")
                    fear_greed_data = {
                        "value": extract_or_none(data, ["data", 0, "value"]),
                        "value_classification": extract_or_none(data, ["data", 0, "value_classification"]),
                        "timestamp": extract_or_none(data, ["data", 0, "timestamp"])
                    }
                print(f"Extracted Fear and Greed data: {fear_greed_data}")
                logging.info(f"Extracted Fear and Greed data: {fear_greed_data}")
                if fear_greed_data["value"] is None or fear_greed_data["value_classification"] is None:
                    msg = f"Failed to extract Fear and Greed data in mock mode: value={fear_greed_data['value']}, classification={fear_greed_data['value_classification']}"
                    print(msg)
                    logging.error(msg)
                    send_telegram_message(msg, telegram_chat_id)
                    return
            except json.JSONDecodeError as e:
                msg = f"Errore parsing JSON nel file mock {fixed_mock_file_path}: {e}"
                print(msg)
                logging.error(msg)
                send_telegram_message(msg, telegram_chat_id)
                return
            except Exception as e:
                msg = f"Errore generico caricamento file mock {fixed_mock_file_path}: {e}"
                print(msg)
                logging.error(msg)
                send_telegram_message(msg, telegram_chat_id)
                return
        else:
            msg = f"Mock file non trovato: {fixed_mock_file_path}. Disabling mock mode and exiting."
            print(msg)
            logging.warning(msg)
            send_telegram_message(msg, telegram_chat_id)
            return
    else:
        print("Making real API call to CoinMarketCap")
        logging.info("Making real API call to CoinMarketCap")
        try:
            # CoinMarketCap: Fear and Greed Index
            print("Fetching Fear and Greed Index from CoinMarketCap")
            cmc_headers = {"X-CMC_PRO_API_KEY": api_configs['coinmarketcap']['key']}
            cmc_fng_response = make_api_request(
                f"{api_configs['coinmarketcap']['url']}/v3/fear-and-greed/historical?limit=1",
                headers=cmc_headers
            )
            cmc_data = cmc_fng_response.json()
            print("CoinMarketCap response received")
            logging.info("CoinMarketCap response received")
            logging.info(f"CoinMarketCap raw response: {json.dumps(cmc_data, indent=2)}")

            cmc_status = cmc_data.get("status", {})
            credit_count = cmc_status.get("credit_count", "unknown")
            print(f"CoinMarketCap call used {credit_count} credits")
            logging.info(f"CoinMarketCap call used {credit_count} credits")

            # Estrai dati con accesso diretto e fallback a extract_or_none
            try:
                fear_greed_data = {
                    "value": cmc_data["data"][0]["value"],
                    "value_classification": cmc_data["data"][0]["value_classification"],
                    "timestamp": cmc_data["data"][0]["timestamp"]
                }
            except (KeyError, IndexError) as e:
                logging.warning(f"Direct access failed: {e}. Falling back to extract_or_none")
                fear_greed_data = {
                    "value": extract_or_none(cmc_data, ["data", 0, "value"]),
                    "value_classification": extract_or_none(cmc_data, ["data", 0, "value_classification"]),
                    "timestamp": extract_or_none(cmc_data, ["data", 0, "timestamp"])
                }
            print(f"Extracted Fear and Greed data: {fear_greed_data}")
            logging.info(f"Extracted Fear and Greed data: {fear_greed_data}")

            if fear_greed_data["value"] is None or fear_greed_data["value_classification"] is None:
                msg = f"Failed to extract Fear and Greed data: value={fear_greed_data['value']}, classification={fear_greed_data['value_classification']}, raw_data={json.dumps(cmc_data, indent=2)}"
                print(msg)
                logging.error(msg)
                send_telegram_message(msg, telegram_chat_id)
                return

            # Salva risposta API
            try:
                with open(mock_filepath, "w", encoding="utf-8") as f:
                    json.dump(cmc_data, f, ensure_ascii=False, indent=2)
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
            send_telegram_message(msg, telegram_chat_id)
            return
        except Exception as e:
            msg = f"Eccezione imprevista durante chiamata API: {e}"
            print(msg)
            logging.error(msg)
            send_telegram_message(msg, telegram_chat_id)
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
        send_telegram_message(msg, telegram_chat_id)
        return

    # Query di inserimento
    insert_sql = """
        INSERT OR IGNORE INTO fear_greed_daily (
            date, value, value_classification, api_timestamp
        )
        VALUES (?, ?, ?, ?)
    """

    # --- 3. Elaborazione e inserimento dati ---
    total_elements = 1  # Solo un record per chiamata
    print(f"Processing Fear and Greed Index for database insertion")
    logging.info(f"Processing Fear and Greed Index for database insertion")

    try:
        values = (
            current_hour_str,
            fear_greed_data.get("value"),
            fear_greed_data.get("value_classification"),
            fear_greed_data.get("timestamp")
        )
        cur.execute(insert_sql, values)
        if cur.rowcount == 1:
            inserted_count += 1
            conn.commit()
            print(f"Inserted Fear and Greed record at {current_hour_str}")
            logging.info(f"Inserted Fear and Greed record at {current_hour_str}")
        else:
            skipped_date_mismatch += 1
            print(f"Fear and Greed record at {current_hour_str} ignored (duplicate PK)")
            logging.info(f"Fear and Greed record at {current_hour_str} ignored (duplicate PK)")
    except Exception as e:
        failed_count += 1
        conn.rollback()
        print(f"Error inserting Fear and Greed record at {current_hour_str}: {e}")
        logging.error(f"Error inserting Fear and Greed record at {current_hour_str}: {e}")

    conn.close()
    print("Closed database connection")
    logging.info("Closed database connection")

    # --- 4. Messaggio Telegram finale ---
    try:
        summary_msg = telegram_msg_templates.get_fear_greed_import_summary(
            total_elements=total_elements,
            inserted_count=inserted_count,
            skipped_date_mismatch=skipped_date_mismatch,
            failed_count=failed_count,
            file_save_status=file_save_status
        )
        print(f"Summary: {summary_msg}")
        if telegram_chat_id:
            send_telegram_message(summary_msg, telegram_chat_id)
        else:
            print("No Telegram chat ID configured")
            logging.warning("No Telegram chat ID configured")
    except Exception as e:
        msg = f"Error generating summary message: {e}"
        print(msg)
        logging.error(msg)
        send_telegram_message(msg, telegram_chat_id)
        summary_msg = f"Processed: {total_elements}, Inserted: {inserted_count}, Skipped: {skipped_date_mismatch}, Errors: {failed_count}, Status: {file_save_status}"

    print("Fear and Greed Index import completed")
    logging.info("Fear and Greed Index import completed")

if __name__ == "__main__":
    try:
        import_fear_greed_data()
    except Exception as e:
        print(f"Unexpected error in script: {e}")
        logging.error(f"Unexpected error in script: {e}")