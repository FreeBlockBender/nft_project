
# app/data_import/import_api.py

import os
import json
import requests
import logging
from datetime import datetime, date
from app.config import load_config
from app.database import get_db_connection
from app.utils.helpers import unix_to_yyyy_mm_dd, unix_to_hh_mm, extract_or_none
from app.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.utils import telegram_msg_templates # Import del modulo per i template

def import_nft_collections_via_api():
    """
    Importa dati sulle collezioni NFT via API o da un file mock locale.
    Salva la risposta API su file (se in modalità API).
    Processa i dati, inserendo i record per la data odierna nella tabella historical_nft_data.
    Fornisce logging dettagliato per ogni elemento processato.
    Invia un riepilogo finale tramite Telegram utilizzando un template.
    """
    config = load_config()
    api_endpoint = config.get("API_ENDPOINT")
    api_key = config.get("QAPIKEY")
    # Assicurati che la variabile di ambiente sia letta correttamente e confrontata con 'true' (case-insensitive)
    mock_mode = str(config.get("MOCK_API_MODE", "false")).lower() == "true"

    today_obj = date.today()
    day_str = today_obj.strftime("%d")
    month_str = today_obj.strftime("%m")
    year_str = today_obj.strftime("%Y")
    data_dir = "data"
    # Percorso dinamico per salvare la risposta API
    auto_mock_filename = f"nftapipricefloor_{day_str}_{month_str}_{year_str}.json"
    auto_mock_filepath = os.path.join(data_dir, auto_mock_filename)

    # Percorso fisso per il file mock locale richiesto
    fixed_mock_file_path = config.get("MOCK_API_LOCAL_FILE", "data/local.json")
    telegram_chat_id = get_monitoring_chat_id()

    data = None # Variabile per conservare il payload JSON processato
    api_response_dump_status = None  # Stato del salvataggio file: None, "success", "error:<msg>", "skipped"

    # --- 1. Caricamento dati (Mock Mode vs API Reale) ---
    if mock_mode:
        # Se MOCK_API_MODE è true, carica SEMPRE da data/local.json
        logging.info(f"Mock mode ATTIVO: caricamento dati da file locale fisso: {fixed_mock_file_path}.")
        try:
            with open(fixed_mock_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            api_response_dump_status = "skipped" # Salvataggio file skippato in mock mode
            logging.info("Dati caricati con successo dal file mock.")
        except FileNotFoundError:
             msg = f"Errore: File mock locale non trovato al percorso specificato: {fixed_mock_file_path}"
             logging.error(msg)
             send_telegram_message(msg, telegram_chat_id)
             return # Esce se il file mock richiesto non esiste
        except json.JSONDecodeError as e:
             msg = f"Errore parsing JSON nel file mock {fixed_mock_file_path}: {e}"
             logging.error(msg)
             send_telegram_message(msg, telegram_chat_id)
             return # Esce se il file mock non è un JSON valido
        except Exception as e:
            msg = f"Errore generico caricamento file mock {fixed_mock_file_path}: {e}"
            logging.error(msg)
            send_telegram_message(msg, telegram_chat_id)
            return # Esce per altri errori di caricamento file

    else:
        # Se MOCK_API_MODE è false, effettua la chiamata API reale
        params = {"qapikey": api_key}
        logging.info("Chiamata API reale in corso...")
        try:
            response = requests.get(api_endpoint, params=params, timeout=60)
            if not response.ok:
                # Gestisce errori HTTP
                msg = f"Errore API! Status: {response.status_code}, Body: {response.text}"
                logging.error(msg)
                send_telegram_message(msg, telegram_chat_id)
                return # Esce in caso di errore API
            # Se tutto ok:
            try:
                data = response.json() # Tenta il parsing JSON della risposta
                logging.info("Risposta API ricevuta e parsata con successo.")
            except Exception as e:
                # Gestisce errori di parsing JSON della risposta API
                msg = f"Errore parsing JSON di risposta API: {e}. Risposta testuale: {response.text[:500]}..." # Logga anche parte della risposta per contesto
                logging.error(msg)
                send_telegram_message(msg, telegram_chat_id)
                return # Esce se il parsing JSON fallisce

            # --- Salva la risposta API su file dinamico ---
            # Quando il payload è un array (o un dict che contiene 'data' array), salviamo il file risposta in /data/
            # Controlliamo la struttura per decidere se salvare
            actual_payload_for_check = data["data"] if isinstance(data, dict) and "data" in data else data
            if isinstance(actual_payload_for_check, list):
                try:
                    os.makedirs(data_dir, exist_ok=True) # Crea la cartella 'data' se non esiste
                    with open(auto_mock_filepath, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2) # Salva l'intero payload ricevuto
                    api_response_dump_status = "success" # Stato successo salvataggio
                    logging.info(f"Risposta API salvata con successo in {auto_mock_filepath}")
                except Exception as e:
                    api_response_dump_status = f"error:{str(e)}" # Stato errore salvataggio con messaggio
                    logging.error(f"Errore salvataggio risposta API su file {auto_mock_filepath}: {e}")
            else:
                # Non salva se il payload non è un array o un dict con 'data' array (che contiene l'array)
                api_response_dump_status = "skipped" # Stato skippato salvataggio
                logging.warning("Risposta API non è un array o dict con 'data' array. Salvataggio file skippato.")

        except requests.exceptions.Timeout:
            # Gestisce timeout della richiesta
            msg = "Errore Eccezione chiamata API: Timeout della richiesta dopo 60 secondi."
            logging.error(msg)
            send_telegram_message(msg, telegram_chat_id)
            return # Esce per timeout
        except requests.exceptions.RequestException as e:
            # Gestisce altri errori di richiesta
            msg = f"Errore Eccezione chiamata API: {e}"
            logging.error(msg)
            send_telegram_message(msg, telegram_chat_id)
            return # Esce per altri errori di richiesta
        except Exception as e:
            # Gestisce altre eccezioni impreviste durante la chiamata API
            msg = f"Eccezione imprevista durante chiamata API: {e}"
            logging.error(msg)
            send_telegram_message(msg, telegram_chat_id)
            return # Esce per eccezione imprevista


    # --- 2. Validazione e preparazione dati per l'inserimento ---
    # Assicurati che 'data' sia l'array di elementi da processare (se era un dict con chiave 'data')
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    # Verifica se i dati sono un array, altrimenti non possiamo iterare
    if not isinstance(data, list):
        msg = "Il payload ricevuto (da mock o API) NON è un array di elementi processabili."
        logging.error(msg)
        send_telegram_message(msg, telegram_chat_id)
        # Se eravamo in modalità API e il salvataggio è avvenuto, includi questa info
        final_save_status = api_response_dump_status if not mock_mode else "skipped"
        # Invia un riepilogo di errore parziale se possibile, ma senza contatori di insert/skip/error
        # Per semplicità, usciamo e il messaggio di errore sopra è sufficiente.
        return

    conn = get_db_connection()
    cur = conn.cursor()

    # Query di inserimento per historical_nft_data
    # Usiamo INSERT OR IGNORE per gestire eventuali duplicati (basato su Primary Key) senza errori che bloccano tutto
    insert_sql = """
        INSERT OR IGNORE INTO historical_nft_data (
            collection_identifier, contract_address, slug, latest_floor_date, latest_floor_timestamp,
            floor_native, floor_usd, chain, chain_currency_symbol, marketplace_source,
            ranking, unique_owners, total_supply, listed_count, best_price_url,
            sale_count_24h, sale_volume_native_24h, highest_sale_native_24h, lowest_sale_native_24h
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Inizializzazione contatori per il riepilogo
    inserted = 0 # Record inseriti correttamente (o ignorati con successo da OR IGNORE, se vogliamo contarli così)
    errors = 0 # Record che hanno generato un'eccezione durante l'elaborazione/insert
    skipped_date_mismatch = 0 # Record saltati perché latest_floor_date non è la data odierna
    total = len(data) # Totale elementi nel payload JSON
    today_str = date.today().strftime("%Y-%m-%d") # Data odierna nel formato YYYY-MM-DD per confronto

    logging.info(f"Inizio elaborazione di {total} elementi JSON per l'inserimento nel DB.")

    # --- 3. Iterazione ed elaborazione per ogni elemento ---
    for item in data:
        # Esegui l'elaborazione di ciascun elemento all'interno di un blocco try-except
        # per isolare gli errori a livello di singolo record.
        slug = extract_or_none(item, ["slug"]) # Estrai lo slug in anticipo per il logging

        try:
            # Estrazione dati con gestione errori
            collection_identifier = extract_or_none(item, ["providerCollectionId"])
            contract_address = extract_or_none(item, ["stats","floorInfo","tokenInfo","contract"])
            latestFloorTs = extract_or_none(item, ["stats", "floorInfo", "latestFloorTs"])
            # Converti timestamp in data YYYY-MM-DD per il confronto
            latest_floor_date = unix_to_yyyy_mm_dd(latestFloorTs) # Restituisce None se latestFloorTs è invalido

            # Controllo: Inserisci solo se la data convertita è uguale a oggi E latestFloorTs è valido
            if latestFloorTs is None or latest_floor_date != today_str:
                skipped_date_mismatch += 1
                # 4. Logging per elemento: Skippato per data non odierna
                logging.info(
                    f"Saltato slug '{slug if slug else 'N/A'}': latestFloorTs={latestFloorTs}, "
                    f"conversione data={latest_floor_date}, data odierna={today_str}. Data non corrispondente o invalida."
                )
                continue # Salta questo elemento e passa al prossimo

            # Se la data corrisponde, estrai i restanti campi
            latest_floor_timestamp = unix_to_hh_mm(latestFloorTs)
            floor_native = extract_or_none(item, ["stats","floorInfo","currentFloorNative"])
            floor_usd = extract_or_none(item, ["stats","floorInfo","currentFloorUsd"])
            chain = extract_or_none(item, ["blockchain"])
            chain_currency_symbol = extract_or_none(item, ["nativeCurrency"])
            marketplace_source = extract_or_none(item, ["stats","floorInfo","tokenInfo","source"])
            ranking = extract_or_none(item, ["ranking"])
            unique_owners = extract_or_none(item, ["stats","totalOwners"])
            total_supply = extract_or_none(item, ["stats","totalSupply"])
            listed_count = extract_or_none(item, ["stats","listedCount"])
            best_price_url = extract_or_none(item, ["bestPriceUrl"])
            sale_count_24h = extract_or_none(item, ["stats","salesTemporalityNative","count","val24h"])
            sale_volume_native_24h = extract_or_none(item, ["stats","salesTemporalityNative","volume","val24h"])
            highest_sale_native_24h = extract_or_none(item, ["stats","salesTemporalityNative","highest","val24h"])
            lowest_sale_native_24h = extract_or_none(item, ["stats","salesTemporalityNative","lowest","val24h"])

            # Prepara la tuple di valori per l'inserimento
            values = (
                collection_identifier, contract_address, slug, latest_floor_date, latest_floor_timestamp,
                floor_native, floor_usd, chain, chain_currency_symbol, marketplace_source,
                ranking, unique_owners, total_supply, listed_count, best_price_url,
                sale_count_24h, sale_volume_native_24h, highest_sale_native_24h, lowest_sale_native_24h
            )

            # Esegue l'inserimento nel database
            cur.execute(insert_sql, values)

            # sqlite3.cur.rowcount è 1 per INSERT, 0 per INSERT IGNORE se ignorato
            if cur.rowcount == 1:
                inserted += 1
                conn.commit() # Committa l'inserimento riuscito
                # 4. Logging per elemento: Inserito correttamente
                logging.info(f"Inserito record per la collezione '{slug if slug else 'N/A'}'.")
            else:
                # Questo caso si verifica con INSERT OR IGNORE se il record è un duplicato della Primary Key
                # Non lo contiamo come 'inserted', ma nemmeno come 'error' o 'skipped_date_mismatch'.
                # Potremmo aggiungere un contatore per "ignorati per duplicato PK" se necessario,
                # ma per ora rientra implicitamente tra quelli che non sono 'inserted' o 'error'.
                logging.info(f"Record per la collezione '{slug if slug else 'N/A'}' già esistente (duplicato PK). Ignorato da INSERT OR IGNORE.")
                # Non incrementa inserted, non incrementa errors, non incrementa skipped_date_mismatch
                # conn.commit() # Non c'è nulla da committare per una riga ignorata

        except Exception as e:
            errors += 1
            conn.rollback() # Annulla eventuali operazioni DB parziali per questa riga
            # 4. Logging per elemento: Errore durante l'elaborazione/insert
            logging.error(f"Errore elaborazione/insert per slug '{slug if slug else 'N/A'}': {type(e).__name__} - {e}.")
            # Continua l'elaborazione del resto degli elementi


    # --- Fine del loop di elaborazione elementi ---
    conn.close() # Chiude la connessione al database al termine

    # --- 5. Messaggio Telegram finale ---
    logging.info("Importazione via API completata. Invio messaggio di riepilogo.")

    # Genera il messaggio di riepilogo utilizzando la funzione dal template file
    # Passa i contatori raccolti e lo stato del salvataggio del file API
    summary_msg = telegram_msg_templates.get_api_import_summary(
        total, # Totale elementi nel JSON
        inserted, # Record inseriti con successo
        skipped_date_mismatch, # Record saltati per data non odierna
        errors, # Record con errori durante l'elaborazione/insert
        api_response_dump_status # Stato del salvataggio del file API
    )

    # Invia il messaggio Telegram
    if telegram_chat_id:
        send_telegram_message(summary_msg, telegram_chat_id)
    else:
        logging.warning("ID chat Telegram non configurato. Impossibile inviare messaggio riepilogativo finale.")

    logging.info("Processo di importazione via API concluso.")


