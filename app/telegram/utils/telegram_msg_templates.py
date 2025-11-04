
# app/utils/telegram_msg_templates.py
from datetime import datetime, date
import random

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
        saving_detail = "Response salvata!"
    elif file_save_status and file_save_status.startswith("error:"):
        saving_detail = f"❌ Errore salvataggio risposta API: {file_save_status.split(':',1)[1]}"
    elif file_save_status == "skipped":
        saving_detail = "Salvataggio risposta API skippato (Mock Mode attivo o payload non array)."
    else:
        saving_detail = "Salvataggio risposta API: stato sconosciuto o non applicabile."


    msg = (
        "🤖 Report Import API\n\n" # Titolo del report
        f"🔎 Oggetti trovati: {total_elements}\n" # Totale elementi processati
        f"✔️ Inseriti: {inserted_count}\n" # Elementi inseriti con successo
        f"⚠️ Skippati (data non odierna): {skipped_date_mismatch}\n" # Elementi saltati per mismatch data
        f"❌ Errori: {failed_count}\n" # Elementi con errori durante l'inserimento
        f"\n💾 {saving_detail}" # Dettaglio salvataggio file
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
        f"📄 Report Import Metadati \n\n" # Titolo del report
        f"📁 {json_filename}\n\n" # Nome del file
        f"🔎Collezioni trovate: {total_elements}.\n" # Totale elementi nel file
        f"✔️ Inseriti: {inserted_count}\n" # Collezioni inserite
        f"🔄 Ignoranti (già presenti): {ignored_count}\n" # Collezioni ignorate da INSERT OR IGNORE
        f"❌ In errore: {error_count}\n" # Errori di elaborazione/insert
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
        f"🗓️ Date: {obj.get('date', 'N/A')}\n"
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
    return (f"✨ Golden Cross Elaboration [{ma_short} , {ma_long}] 📈\n\n"
            f"📌 Type: {mode}\n "
            f"🔎 Found: {total_crosses}\n"
            f"💾 Saved in DB: {inserted_records}")


def format_golden_cross_monthly_recap_msg(
    crosses,
    ma_short_period,
    ma_long_period,
    today_str
):
    """
    Costruisce il messaggio riepilogativo mensile delle golden cross secondo il template richiesto.
    crosses: lista di dict con tutti i dati necessari per ogni cross
    ma_short_period, ma_long_period: interi - valori delle medie mobili utilizzate
    today_str: stringa data corrente nel formato DD-MM-YYYY
    """

    header = f"*** GOLDEN CROSS MONTHLY RECAP ({ma_short_period},{ma_long_period}) ***"
    rows = []

    for idx, cross in enumerate(crosses, 1):
        slug = cross["slug"]
        chain = cross["chain"]
        is_native = cross["is_native"]
        # Floor e symbol per golden cross day
        if is_native:
            original_floor = cross["floor_native"]
            currency = cross["chain_currency_symbol"]
        else:
            original_floor = cross["floor_usd"]
            currency = "usd"

        gc_date = datetime.strptime(cross["date"], "%Y-%m-%d").strftime("%d-%m-%Y")

        # Floor e symbol attuali
        if is_native:
            current_floor = cross["current_floor_native"]
        else:
            current_floor = cross["current_floor_usd"]

        ## percentuale profit
        if original_floor and current_floor and original_floor != 0:
            profit = ((current_floor - original_floor) / original_floor) * 100
            profit_str = f"{profit:+.0f}% "
            profit_str += "🟢" if profit >= 0 else "🔴"
        else:
            profit_str = "n.d."

        row = (
            f"{idx}. - {slug}, {chain}, original floor: {original_floor:g} {currency} on {gc_date}, "
            f"now {current_floor:g} {currency} on {today_str}, profit {profit_str}"
        )
        rows.append(row)

    return f"{header}\n\n" + "\n\n".join(rows) if rows else f"{header}\n\nNessuna Golden Cross rilevata nell'ultimo mese."


def format_golden_cross_x_msg(obj) -> str:
    """
    Create a concise Golden Cross message for X.
    Rounds floor_native to 4 decimals, floor_usd to 2 decimals, MA short/long to 4 decimals.
    Uses dynamic MA periods and appropriate currency suffix.
    """
    floor_native = f"{obj.get('floor_native', 0):.4f}" if obj.get('floor_native') is not None else "N/A"
    floor_usd = f"{obj.get('floor_usd', 0):.2f}" if obj.get('floor_usd') is not None else "N/A"
    ma_short = f"{obj.get('ma_short', 0):.4f}" if obj.get('ma_short') is not None else "N/A"
    ma_long = f"{obj.get('ma_long', 0):.4f}" if obj.get('ma_long') is not None else "N/A"

    # Dynamic MA periods
    period_short = obj.get('ma_short_period', "short")
    period_long = obj.get('ma_long_period', "long")

    # Currency suffix for MA
    currency = obj.get('chain_currency_symbol', '') if obj.get('is_native', 1) in (1, "1", True) else "USD"

    # Currency suffix for floor price
    currency_floor = obj.get('chain_currency_symbol', '') 

    # Collection slug for mention and hashtag
    slug = obj.get('slug', 'Unknown')
    collection_name = obj.get('name', slug)
    x_handle = obj.get('x_page', None)
    slug_mention = f"{x_handle}" if x_handle is not None else slug

    # Safe hashtag generation, removing spaces and hyphens
    hashtag_name = collection_name.replace(' ', '').replace('-', '') if isinstance(collection_name, str) else 'Unknown'

    cta_phrases = [
        "Snag one here",
        "Check it out",
        "Grab yours now",
        "Dive in here",
        "Explore now"
    ]

    cta_phrase = random.choice(cta_phrases)

    # Construct the message
    msg = (
        f"🚨 GOLDEN CROSS ALERT! 🚀\n\n"
        f"{collection_name} by {slug_mention} NFTs on #{obj.get('chain', 'N/A')} signal a BULLISH trend!\n\n"
        f"📈 MA{period_short} ({ma_short} {currency}) crossed above MA{period_long} ({ma_long} {currency}).\n"
        f"Floor: {floor_native} {currency_floor} (~${floor_usd}). "
        f"{obj.get('total_supply', 'N/A')} supply, {obj.get('unique_owners', 'N/A')} owners, {obj.get('listed_count', 'N/A')} listed.\n\n"
        f"#NFTCommunity #NFTs #{obj.get('chain', 'N/A')} #{hashtag_name} #GoldenCross #CryptoArt \n\n"
        f"{cta_phrase}: {obj.get('best_price_url')}" if obj.get('best_price_url') is not None else ""

    )

    return msg


def format_golden_cross_farcaster_msg(obj) -> str:
    """
    Create a concise Golden Cross message for Farcaster.
    Handles farcaster_page as channel (/name) or user (@name).
    Rounds floor_native to 4 decimals, floor_usd to 2 decimals, MA short/long to 4 decimals.
    Uses dynamic MA periods, marketplace_url, and fits 320 chars.
    """
    floor_native = f"{obj.get('floor_native', 0):.4f}" if obj.get('floor_native') is not None else "N/A"
    floor_usd = f"{obj.get('floor_usd', 0):.2f}" if obj.get('floor_usd') is not None else "N/A"
    ma_short = f"{obj.get('ma_short', 0):.4f}" if obj.get('ma_short') is not None else "N/A"
    ma_long = f"{obj.get('ma_long', 0):.4f}" if obj.get('ma_long') is not None else "N/A"

    period_short = obj.get('ma_short_period', "short")
    period_long = obj.get('ma_long_period', "long")
    currency = obj.get('chain_currency_symbol', 'ETH') if obj.get('is_native', 1) in (1, "1", True) else "USD"
    currency_floor = obj.get('chain_currency_symbol', 'ETH')
    slug = obj.get('slug', 'Unknown')
    collection_name = obj.get('name', slug)
    
    # Handle farcaster_page as channel or user
    farcaster_page = obj.get('farcaster_page', None)
    if farcaster_page and farcaster_page.startswith('/'):
        # Channel (e.g., /base)
        slug_mention = f"{farcaster_page[1:]}"  # e.g., "base channel"
    elif farcaster_page and farcaster_page.startswith('@'):
        # User handle (e.g., @CoolBaseNFTs)
        slug_mention = farcaster_page
    else:
        slug_mention = slug

    cta_phrases = ["Snag one", "Check it", "Grab now", "Dive in", "Explore"]
    cta_phrase = random.choice(cta_phrases)

    msg = (
        f"🚨 GOLDEN CROSS on {collection_name} by {slug_mention}! 🚀\n"
        f"📈 MA{period_short} ({ma_short} {currency}) > MA{period_long} ({ma_long} {currency}).\n"
        f"Floor: {floor_native} {currency_floor} (~${floor_usd}). "
        f"{cta_phrase}: {obj.get('best_price_url', '')}"
    )
    return msg[:320]




def get_fear_greed_import_summary(
    total_elements: int,
    inserted_count: int,
    skipped_date_mismatch: int,
    failed_count: int,
    file_save_status: str
) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione del Fear and Greed Index.

    Args:
        total_elements: Numero totale di elementi processati (di solito 1 per il Fear and Greed Index).
        inserted_count: Numero di record inseriti correttamente.
        skipped_date_mismatch: Numero di record saltati (e.g., per chiave primaria duplicata).
        failed_count: Numero di record con errori durante l'insert.
        file_save_status: Stato del salvataggio del file JSON (successo, errore, skippato).

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    # Preparazione dettaglio salvataggio file
    if file_save_status == "success":
        saving_detail = "Risposta API salvata correttamente."
    elif file_save_status and file_save_status.startswith("error:"):
        saving_detail = f"❌ Errore salvataggio risposta API: {file_save_status.split(':', 1)[1]}"
    elif file_save_status == "skipped":
        saving_detail = "Salvataggio risposta API skippato (Mock Mode attivo)."
    else:
        saving_detail = "Salvataggio risposta API: stato sconosciuto o non applicabile."

    msg = (
        "📊 Report Import Fear and Greed Index 📈\n\n"
        f"Totale elementi processati: {total_elements}\n"
        f"✔️ Record inseriti: {inserted_count}\n"
        f"🔸 Record saltati (duplicati): {skipped_date_mismatch}\n"
        f"❌ Record con errori di insert: {failed_count}\n"
        f"\n💾 Stato Salvataggio File JSON:\n{saving_detail}"
    )
    return msg


def get_crypto_import_summary(
    total_elements: int,
    inserted_count: int,
    skipped_date_mismatch: int,
    failed_count: int,
    file_save_status: str
) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione dei dati cripto da CoinGecko.

    Args:
        total_elements: Numero totale di elementi processati (criptovalute nel payload JSON).
        inserted_count: Numero di record inseriti correttamente.
        skipped_date_mismatch: Numero di record saltati (e.g., per chiave primaria duplicata).
        failed_count: Numero di record con errori durante l'insert.
        file_save_status: Stato del salvataggio del file JSON (successo, errore, skippato).

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    # Preparazione dettaglio salvataggio file
    if file_save_status == "success":
        saving_detail = "Risposta API salvata correttamente."
    elif file_save_status and file_save_status.startswith("error:"):
        saving_detail = f"❌ Errore salvataggio risposta API: {file_save_status.split(':', 1)[1]}"
    elif file_save_status == "skipped":
        saving_detail = "Salvataggio risposta API skippato (Mock Mode attivo)."
    else:
        saving_detail = "Salvataggio risposta API: stato sconosciuto o non applicabile."

    msg = (
        "💰 Report Import Dati Cripto 📈\n\n"
        f"Totale criptovalute processate: {total_elements}\n"
        f"✔️ Record inseriti: {inserted_count}\n"
        f"🔸 Record saltati (duplicati): {skipped_date_mismatch}\n"
        f"❌ Record con errori di insert: {failed_count}\n"
        f"\n💾 Stato Salvataggio File JSON:\n{saving_detail}"
    )
    return msg


def get_historical_crypto_import_summary(
    total_elements: int,
    inserted_count: int,
    skipped_date_mismatch: int,
    failed_count: int,
    file_save_status: str
) -> str:
    """
    Genera il messaggio di riepilogo per il processo di importazione dei dati storici cripto.

    Args:
        total_elements: Numero totale di elementi processati (record di prezzo giornalieri).
        inserted_count: Numero di record inseriti correttamente.
        skipped_date_mismatch: Numero di record saltati (e.g., per chiave primaria duplicata).
        failed_count: Numero di record con errori durante l'insert.
        file_save_status: Stato del salvataggio del file JSON (successo, errore, skippato).

    Returns:
        La stringa formattata per il messaggio Telegram.
    """
    if file_save_status == "success":
        saving_detail = "Risposta API salvata correttamente."
    elif file_save_status and file_save_status.startswith("error:"):
        saving_detail = f"❌ Errore salvataggio risposta API: {file_save_status.split(':', 1)[1]}"
    elif file_save_status == "skipped":
        saving_detail = "Salvataggio risposta API skippato (Mock Mode attivo)."
    else:
        saving_detail = "Salvataggio risposta API: stato sconosciuto o non applicabile."

    msg = (
        "📅 Report Import Dati Storici Cripto 📈\n\n"
        f"Totale record processati: {total_elements}\n"
        f"✔️ Record inseriti: {inserted_count}\n"
        f"🔸 Record saltati (duplicati): {skipped_date_mismatch}\n"
        f"❌ Record con errori di insert: {failed_count}\n"
        f"\n💾 Stato Salvataggio File JSON:\n{saving_detail}"
    )
    return msg