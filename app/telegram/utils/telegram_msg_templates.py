
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

def format_golden_cross_msg(obj) -> str:
    """
    Crea il messaggio per la Golden Cross.
    Arrotonda a due cifre floor_native e floor_usd.
    MA short/long arrotondati a 5 cifre e visualizzati con currency appropriata:
    Integra ora i valori a partire da ma_short_period / ma_long_period dinamici.
    """
    floor_native = f"{obj.get('floor_native', None):.4f}" if obj.get('floor_native') is not None else "N/A"
    floor_usd = f"{obj.get('floor_usd', None):.2f}" if obj.get('floor_usd') is not None else "N/A"
    ma_short = f"{obj.get('ma_short', None):.4f}" if obj.get('ma_short') is not None else "N/A"
    ma_long = f"{obj.get('ma_long', None):.4f}" if obj.get('ma_long') is not None else "N/A"

    # Nuovo: periodi dinamici di MA
    period_short = obj.get('ma_short_period', "short")
    period_long = obj.get('ma_long_period', "long")

    # Determina sufisso per MA (simbolo valuta)
    if obj.get('is_native', 1) in (1, "1", True):  # gestisce possibili tipi diversi
        ma_suffix = f" {obj.get('chain_currency_symbol', '')}"
    else:
        ma_suffix = " USD"

    msg = (
        f"🔔 **GOLDEN CROSS DETECTED!**\n\n"
        f"🏷️ Slug: {obj.get('slug', 'N/A')}\n"
        f"🥇 Ranking: {obj.get('ranking','N/A')}\n"
        f"💰 Floor Price (Native): {floor_native} {obj.get('chain_currency_symbol','')}\n"
        f"💵 Floor Price (USD): {floor_usd}\n"
        f"📜 CA: {obj.get('contract_address','N/A')}\n"
        f"🔗 Blockchain: {obj.get('chain','N/A')}\n"
        f"👤 Unique Owners: {obj.get('unique_owners','N/A')}\n"
        f"🧱 Total Supply: {obj.get('total_supply','N/A')}\n"
        f"📈 Listed Count: {obj.get('listed_count','N/A')}\n"
        f"⚡ MA short ({period_short}): {ma_short} {ma_suffix}\n"
        f"⚡ MA long ({period_long}): {ma_long} {ma_suffix}\n\n"
        f"🔎 Best Price Url: ({obj.get('best_price_url','')})"
    )
    return msg

def get_golden_cross_summary_msg(mode, ma_short, ma_long, total_crosses, inserted_records):
    """
    Genera un messaggio di riepilogo elaborazione Golden Cross.

    Args:
        mode (str): 'historical' o 'current'
        ma_short (int): periodo short della media mobile
        ma_long (int): periodo long della media mobile
        total_crosses (int): tot Golden Cross rilevate
        inserted_records (int): effettivi record aggiunti nel DB

    Returns:
        str: messaggio Telegram formattato
    """
    return (f"✨➕📈💰 Golden Cross Elaboration Recap ✨➕📈💰 \n\n"
            f"📌 Golden Cross type: {mode}\n "
            f"📊 SMA used: {ma_short} , {ma_long}\n "
            f"🔎 Golden Cross found: {total_crosses}\n"
            f"💾 Golden Cross saved in DB : {inserted_records}")