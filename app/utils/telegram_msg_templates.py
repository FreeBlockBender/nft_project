
# app/utils/telegram_msg_templates.py

def get_csv_import_summary(total_files_found: int, files_processed_successfully: int, files_skipped: int, total_row_errors: int) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione CSV.

    Args:
        total_files_found: Numero totale di file CSV trovati nella cartella.
        files_processed_successfully: Numero di file elaborati senza errori a livello di riga.
        files_skipped: Numero di file saltati perché già presenti nel database.
        total_row_errors: Numero totale di errori riscontrati durante l'elaborazione delle singole righe.

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    msg = (
        "📊 Recap Import CSV storici \n\n" # Titolo del report
        f"🔍 File trovati nella cartella: {total_files_found}\n" # Totale file individuati
        f"✅ File elaborati con successo: {files_processed_successfully}\n" # File processati senza errori per riga
        f"⏩ File saltati (precedentemente elabolati): {files_skipped}\n" # File ignorati dal check iniziale
        f"❌ Errori durante elaborazione righe: {total_row_errors}\n\n" # Errori specifici sulle singole righe
    )
    return msg


def get_api_import_summary(total_elements: int, inserted_count: int, skipped_date_mismatch: int, failed_count: int, file_save_status: str) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione da API.

    Args:
        total_elements: Numero totale di elementi nell'array JSON.
        inserted_count: Numero di record inseriti correttamente.
        skipped_date_mismatch: Numero di record saltati per data non odierna.
        failed_count: Numero di record con errori durante l'insert.
        file_save_status: Stato del salvataggio del file JSON (successo, errore, skippato).

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    # Preparazione dettaglio salvataggio file
    if file_save_status == "success":
        saving_detail = "Risposta API salvata correttamente."
    elif file_save_status and file_save_status.startswith("error:"):
        saving_detail = f"❌ Errore salvataggio risposta API: {file_save_status.split(':',1)[1]}"
    elif file_save_status == "skipped":
        saving_detail = "Salvataggio risposta API skippato (Mock Mode attivo o payload non array)."
    else:
        saving_detail = "Salvataggio risposta API: stato sconosciuto o non applicabile."


    msg = (
        "🤖 Report Import API NFT Collections 📈\n\n" # Titolo del report
        f"Totale elementi nel payload JSON: {total_elements}\n" # Totale elementi processati
        f"✔️ Record inseriti: {inserted_count}\n" # Elementi inseriti con successo
        f"🔸 Record saltati (data non odierna): {skipped_date_mismatch}\n" # Elementi saltati per mismatch data
        f"❌ Record con errori di insert: {failed_count}\n" # Elementi con errori durante l'inserimento
        f"\n💾 Status Salvataggio File JSON:\n{saving_detail}" # Dettaglio salvataggio file
    )
    return msg

def get_collections_import_summary(json_filename: str, total_elements: int, inserted_count: int, ignored_count: int, error_count: int) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione NFT collections da file.

    Args:
        json_filename: Nome del file JSON processato.
        total_elements: Numero totale di elementi nel file.
        inserted_count: Numero di collezioni inserite come nuove.
        ignored_count: Numero di collezioni ignorate (già presenti).
        error_count: Numero di errori riscontrati durante l'elaborazione.

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    msg = (
        f"📁 Report Import Metadati \n\n" # Titolo del report
        f"File processato: {json_filename}\n" # Nome del file
        f"Totale elementi nel file: {total_elements}.\n" # Totale elementi nel file
        f"✔️ Record inseriti (nuovi): {inserted_count}\n" # Collezioni inserite
        f"⚠️ Record ignorati (già presenti): {ignored_count}\n" # Collezioni ignorate da INSERT OR IGNORE
        f"❌ Errori durante l'elaborazione: {error_count}\n" # Errori di elaborazione/insert
    )
    return msg