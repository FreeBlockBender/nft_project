import os
import csv
import logging
from datetime import datetime
from app.database.database import get_db_connection
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.config.config import load_config

# Configura logging
logging.basicConfig(level=logging.INFO)

def import_csv_folder():
    """
    Importa tutti i file CSV dalla cartella specificata in .env nella tabella historical_nft_data.
    - Per ogni file, estrae il contract_address dal nome file.
    - Per ogni riga, tenta direttamente la INSERT.
    - Se si verifica un errore per chiave primaria duplicata o vincolo di unicità violato,
      incrementa il contatore delle righe skippate, logga e continua.
    - Logging dettagliato su ogni inserimento/skipped/errore.
    - Messaggio Telegram riepilogativo alla fine di tutti i file.
    """

    config = load_config()
    csv_folder = config.get("CSV_HISTORICAL_DATA_PATH")

    if not csv_folder:
        logging.error("Variabile CSV_HISTORICAL_DATA_PATH non trovata in .env.")
        return

    telegram_chat_id = get_monitoring_chat_id()

    # Contatori globali
    total_files_processed = 0
    total_rows_inserted = 0
    total_rows_skipped = 0
    total_rows_errors = 0

    if not os.path.isdir(csv_folder):
        logging.error(f"La cartella CSV '{csv_folder}' non esiste!")
        return

    csv_files = [f for f in os.listdir(csv_folder)
                 if f.endswith('.csv') and os.path.isfile(os.path.join(csv_folder, f))]

    if not csv_files:
        logging.info("Nessun file CSV da processare.")
        return

    for filename in csv_files:
        full_path = os.path.join(csv_folder, filename)
        contract_address = os.path.splitext(filename)[0]  # Estraggo senza estensione

        inserted_rows = 0
        skipped_rows = 0
        row_errors = 0
        total_rows = 0
        row_num = 0

        logging.info(f"[{filename}] Inizio elaborazione file -- {filename}")

        # Conta righe file (escluso header)
        with open(full_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            header = next(reader, None)
            total_rows = sum(1 for _ in reader)
            csvfile.seek(0)
            next(reader, None)

            logging.info(f"[{filename}] Numero totale righe (escluso header): {total_rows}")

            conn = get_db_connection()
            cur = conn.cursor()
            for row in reader:
                row_num += 1
                try:
                    # Adatta qui all'ordine delle colonne del tuo CSV!
                    collection_identifier = row[0]
                    latest_floor_date = row[1]
                    # ... aggiungi qui l'extract degli altri campi necessari per la tua tabella ...

                    # Normalizza la data (assumendo sia 'YYYY-MM-DD')
                    try:
                        date_obj = datetime.strptime(latest_floor_date, "%Y-%m-%d")
                        norm_date = date_obj.strftime("%Y-%m-%d")
                    except Exception as e:
                        row_errors += 1
                        logging.error(f"[{filename}] Riga {row_num}: ERRORE data non valida — {row} — {e}")
                        continue

                    # ---- PROVA DIRETTAMENTE LA INSERT ----
                    insert_sql = """
                        INSERT OR IGNORE INTO historical_nft_data (
                            collection_identifier, contract_address, slug, latest_floor_date, latest_floor_timestamp,
                            floor_native, floor_usd, chain, chain_currency_symbol, marketplace_source,
                            ranking, unique_owners, total_supply, listed_count, best_price_url,
                            sale_count_24h, sale_volume_native_24h, highest_sale_native_24h, lowest_sale_native_24h
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    values = (
                        row[1],               # 1: collection_identifier (non presente nel CSV storico)
                        row[2],             # 2: contract_address (estratto dal nome file)
                        None,               # 3: slug (non presente nel CSV storico)
                        norm_date,          # 4: latest_floor_date (data dal CSV col 1)
                        None,               # 5: latest_floor_timestamp (non presente nel CSV storico)
                        floor_native_value, # 6: floor_native (valore float dal CSV col 2)
                        None,               # 7: floor_usd (non presente nel CSV storico)
                        row[0],               # 8: chain (non presente nel CSV storico)
                        None,               # 9: chain_currency_symbol (non presente nel CSV storico)
                        None,               # 10: marketplace_source (non presente nel CSV storico)
                        None,               # 11: ranking (non presente nel CSV storico)
                        None,               # 12: unique_owners (non presente nel CSV storico)
                        None,               # 13: total_supply (non presente nel CSV storico)
                        None,               # 14: listed_count (non presente nel CSV storico)
                        None,               # 15: best_price_url (non presente nel CSV storico)
                        None,               # 16: sale_count_24h (non presente nel CSV storico)
                        None,               # 17: sale_volume_native_24h (non presente nel CSV storico)
                        None,               # 18: highest_sale_native_24h (non presente nel CSV storico)
                        None                # 19: lowest_sale_native_24h (non presente nel CSV storico)
                    )

                    try:
                        cur.execute(insert_sql, values)
                        conn.commit()
                        inserted_rows += 1
                        logging.info(f"[{filename}] Riga {row_num}: INSERITA [collection_id={collection_identifier}, date={norm_date}]")
                    except Exception as insert_exc:
                        # ---- GESTIONE ERRORE DI CHIAVE UNICA/PRIMARIA ----
                        if "UNIQUE constraint failed" in str(insert_exc) or "duplicate key" in str(insert_exc).lower():
                            skipped_rows += 1
                            logging.info(f"[{filename}] Riga {row_num}: SKIPPED (record già esistente) [collection_id={collection_identifier}, date={norm_date}]")
                        else:
                            row_errors += 1
                            logging.error(f"[{filename}] Riga {row_num}: ERRORE durante inserimento — {row} — {type(insert_exc).__name__} - {insert_exc}")

                except Exception as e:
                    row_errors += 1
                    logging.error(f"[{filename}] Riga {row_num}: ERRORE GENERICO — {row} — {type(e).__name__} - {e}")

            conn.close()

        # ---- RIEPILOGO DOPO IL FILE ----
        logging.info(
            f"[{filename}] RIEPILOGO: Totale righe: {total_rows}, Inserite: {inserted_rows}, "
            f"Skippate: {skipped_rows}, Errori: {row_errors}"
        )

        # Aggiorna i contatori globali
        total_files_processed += 1
        total_rows_inserted += inserted_rows
        total_rows_skipped += skipped_rows
        total_rows_errors += row_errors

    # ---- MESSAGGIO TELEGRAM FINALE ----
    summary_msg = (
        f"Importazione CSV completata.\n"
        f"File elaborati: {total_files_processed}\n"
        f"Insert effettuate: {total_rows_inserted}\n"
        f"Righe skippate: {total_rows_skipped}\n"
        f"Errori: {total_rows_errors}"
    )
    if get_monitoring_chat_id():
        send_telegram_message(summary_msg, get_monitoring_chat_id())
    else:
        logging.warning("ID chat Telegram non configurato. Impossibile inviare messaggio riepilogativo.")

if __name__ == "__main__":
    import_csv_folder()