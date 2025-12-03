import asyncio
import os
import json
import logging
from datetime import date
from app.database.database import get_db_connection
from app.utils.helpers import extract_or_none
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
from app.telegram.utils import telegram_msg_templates  # Import del modulo per i template


def import_collections():
    # Calcola data odierna per il filename
    today = date.today()
    day_str = today.strftime("%d")
    month_str = today.strftime("%m")
    year_str = today.strftime("%Y")
    data_dir = "data"
    json_filename = f"nftapipricefloor_{day_str}_{month_str}_{year_str}.json"
    json_path = os.path.join(data_dir, json_filename)

    telegram_chat_id = get_monitoring_chat_id()

    logging.info("Avvio importazione NFT collections da file storico...")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logging.info(f"Dati caricati con successo da {json_path}.")
    except FileNotFoundError:
        msg = f"Errore: File non trovato - {json_path}. Assicurati che il file esista."
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        return
    except json.JSONDecodeError as e:
        msg = f"Errore parsing JSON nel file {json_path}: {e}"
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        return
    except Exception as e:
        msg = f"Errore generico caricamento file {json_path}: {e}"
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        return

    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    if not isinstance(data, list):
        msg = "Il payload del file non è un array di oggetti come previsto."
        logging.error(msg)
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
        return

    conn = get_db_connection()
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO nft_collections (
            collection_identifier, contract_address, slug, name, chain, chain_currency_symbol, categories
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """

    inserted = 0
    errors = 0
    skipped = 0
    total = len(data)
    processed_count = 0

    for item in data:
        processed_count += 1
        try:
            collection_identifier = extract_or_none(item, ["providerCollectionId"])
            contract_address = extract_or_none(item, ["stats", "floorInfo", "tokenInfo", "contract"])
            slug = extract_or_none(item, ["slug"])
            name = extract_or_none(item, ["name"])
            chain = extract_or_none(item, ["blockchain"])
            chain_currency_symbol = extract_or_none(item, ["nativeCurrency"])

            categories_list = extract_or_none(item, ["types"])
            categories = ", ".join(categories_list) if isinstance(categories_list, list) else None

            if not collection_identifier or not chain:
                errors += 1
                logging.warning(f"Record saltato per mancanza identificativi: {item.get('slug', 'N/A')}")
                continue

            # Controllo se esiste già un record con gli stessi dati
            cur.execute("""
                SELECT 1 FROM nft_collections
                WHERE collection_identifier = ?
                  AND slug = ?
                  AND name = ?
                  AND chain = ?
                  AND chain_currency_symbol = ?
                  AND categories = ?
            """, (
                collection_identifier,
                slug,
                name,
                chain,
                chain_currency_symbol,
                categories
            ))

            if cur.fetchone():
                skipped += 1
                logging.info(f"Record già presente, skippato: {slug} ({collection_identifier} on {chain})")
                continue

            # Inserimento
            cur.execute(insert_sql, (
                collection_identifier,
                contract_address,
                slug,
                name,
                chain,
                chain_currency_symbol,
                categories
            ))
            conn.commit()
            inserted += 1
            logging.info(f"Inserita nuova collezione: {slug} ({collection_identifier} on {chain})")

        except Exception as e:
            errors += 1
            item_identifier = item.get('slug', item.get('providerCollectionId', f"item_{processed_count}"))
            logging.error(f"Errore durante l'elaborazione di '{item_identifier}': {type(e).__name__} - {e}")

    conn.close()

    ignored_count = total - inserted - skipped - errors

    logging.info("Importazione NFT Collections completata. Invio messaggio di riepilogo.")

    summary_msg = telegram_msg_templates.get_collections_import_summary(
        json_filename,
        total,
        inserted,
        skipped,
        errors
    )

    if telegram_chat_id:
        asyncio.run(send_telegram_message(msg, telegram_chat_id))
    else:
        logging.warning("ID chat Telegram non configurato. Impossibile inviare messaggio riepilogativo finale.")

    logging.info("Processo di importazione NFT Collections concluso.")
