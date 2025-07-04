import os
import logging
import sqlite3
import matplotlib.pyplot as plt
import io
from datetime import datetime
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from telegram.constants import ParseMode

from app.utils.moving_average import calculate_sma, count_days_present

# ------- Configurazione iniziale -------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "nft_data.sqlite3")
ALLOWED_TELEGRAM_IDS = set(
    int(x.strip())
    for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",")
    if x.strip()
)

# ------- Comandi autocomplete con descrizione -------
COMMANDS = [
    BotCommand("start", "Mostra messaggio di benvenuto"),
    BotCommand("slug_list_by_prefix", "Lista slug che iniziano con una lettera"),
    BotCommand("slug_list_by_chain", "Lista slug filtrati per chain"),
    BotCommand("slug_list_by_category", "Lista slug filtrati per categoria"),
    BotCommand("meta", "Mostra i metadati di una collezione NFT"),
    BotCommand("ma", "Analisi floor price e medie mobili"),
]

# ------- Logging -------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------- Helper autorizzazione -------
def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_TELEGRAM_IDS

# ------- Funzione per generare il grafico dei floor price e SMA -------
def create_nft_chart(slug: str, data: list, field: str, chain: str):
    """
    Genera un grafico dei floor price e delle medie mobili per una collezione NFT.
    
    Args:
        slug (str): Slug della collezione NFT.
        data (list): Lista di tuple (data, floor_price) dalla tabella historical_nft_data.
        field (str): Campo da plottare ('floor_native' o 'floor_usd').
        chain (str): Chain della collezione (per il titolo e l'etichetta).
    
    Returns:
        BytesIO: Buffer contenente l'immagine del grafico in formato PNG.
    """
    if not data:
        return None
    
    # Estrai date e valori
    dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
    values = [row[1] for row in data if row[1] is not None and str(row[1]).replace('.', '').replace('-', '').isdigit()]
    if not values:
        return None
    
    # Crea una serie temporale continua (interpolazione lineare per gap)
    from scipy.interpolate import interp1d
    import numpy as np
    
    # Converti date in timestamp numerici per l'interpolazione
    date_nums = np.array([d.timestamp() for d in dates])
    value_nums = np.array(values, dtype=np.float64)
    
    # Crea una griglia temporale continua
    date_min = min(dates)
    date_max = max(dates)
    date_range = np.linspace(date_min.timestamp(), date_max.timestamp(), len(dates) * 10)
    interp_func = interp1d(date_nums, value_nums, kind='linear', fill_value="extrapolate")
    interp_values = interp_func(date_range)
    interp_dates = [datetime.fromtimestamp(ts) for ts in date_range]
    
    # Calcola le medie mobili con interpolazione
    date_value_list = [(d.strftime("%Y-%m-%d"), float(v) if v is not None and str(v).replace('.', '').replace('-', '').isdigit() else np.nan) for d, v in zip(dates, [row[1] for row in data])]
    end_date = date_max.strftime("%Y-%m-%d")
    periods = [
        (20, 1, "SMA20"),
        (50, 3, "SMA50"),
        (100, 5, "SMA100"),
        (200, 10, "SMA200"),
    ]
    sma_data = {}
    for period, threshold, label in periods:
        sma_values = []
        for i in range(len(interp_dates)):
            window_end = interp_dates[i].strftime("%Y-%m-%d")
            sma = calculate_sma(date_value_list, period, window_end, missing_threshold=threshold)
            sma_values.append(sma if not np.isnan(sma) else np.nan)
        # Interpolazione lineare per SMA
        sma_nums = np.array(sma_values)
        sma_interp = interp1d(np.arange(len(sma_nums)), sma_nums, kind='linear', fill_value="extrapolate")
        sma_data[label] = sma_interp(np.linspace(0, len(sma_nums)-1, len(interp_dates)))
        # Debug: verifica i valori SMA
        print(f"{label} values: {sma_values[:10]}...")  # Stampa i primi 10 valori per debug
    
    # Crea il grafico
    plt.figure(figsize=(12, 6))
    plt.plot(interp_dates, interp_values, label=f"Floor Price ({field})", color="blue", linewidth=2)
    
    # Plot delle medie mobili
    colors = {"SMA20": "orange", "SMA50": "green", "SMA100": "red", "SMA200": "purple"}
    for label, sma_values in sma_data.items():
        plt.plot(interp_dates, sma_values, label=label, color=colors[label], linestyle="-", linewidth=1.5)
    
    # Personalizza il grafico
    currency_label = chain.upper() if field == "native" else "USD"
    plt.title(f"Floor Price e Medie Mobili per {slug} ({chain}) - Ultimi 200 giorni")
    plt.xlabel("Data")
    plt.ylabel(f"Prezzo ({currency_label})")
    plt.grid(True)
    plt.legend()
    plt.xticks(rotation=45)
    
    # Salva il grafico in memoria
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", bbox_inches="tight")
    buffer.seek(0)
    plt.close()
    return buffer

async def access_denied(update: Update):
    if update.message:
        await update.message.reply_text("Access denied", reply_markup=ReplyKeyboardRemove())
    elif update.callback_query:
        await update.callback_query.answer("Access denied", show_alert=True)

# ------- Connessione DB -------
def get_db_connection():
    return sqlite3.connect(DB_PATH)

# ------- /start handler -------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    await update.message.reply_text(
        f"Benvenuto o Bentornato!\n\n"
        f"Con questo bot potrai:\n"
        f"🔍 Cercare le collezioni per chain, categoria o prefisso.\n"
        f"ℹ️ Visualizzare i metadati di uno slug.\n"
        f"📈 Consultare le diverse medie mobili di una collection.\n\n"
        f"CEO: Ser Basato 💀\n"
        f"CTO: Ser Muay Thai 🥊 🇹🇭\n"
        f"© All rights reserved\n",
        reply_markup=ReplyKeyboardRemove()
    )

# ------- Utility per paginazione -------
def get_paginated_results(results, page, page_size=10):
    start = page * page_size
    end = start + page_size
    page_results = results[start:end]
    total_pages = (len(results) - 1) // page_size + 1 if results else 1
    return page_results, total_pages

def build_pagination_keyboard(command, query_value, page, total_pages):
    keyboard = []
    if page > 0:
        keyboard.append(
            InlineKeyboardButton("⬅️", callback_data=f"{command}|{query_value}|{page-1}")
        )
    if page < (total_pages - 1):
        keyboard.append(
            InlineKeyboardButton("➡️", callback_data=f"{command}|{query_value}|{page+1}")
        )
    if keyboard:
        return InlineKeyboardMarkup([keyboard])
    else:
        return None

# ------- Comando generico paginato -------
async def paginated_list_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    query: str,
    query_value: str,
    command: str,
    page: int = 0,
    field: str = "slug"
):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, (query_value,))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()

    page_results, total_pages = get_paginated_results(results, page)
    if not page_results:
        text = "No results found."
    else:
        text = "\n".join(page_results)
        text = f"Risultati (pagina {page+1}/{total_pages}):\n{text}"

    reply_markup = build_pagination_keyboard(command, query_value, page, total_pages)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup or ReplyKeyboardRemove())
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup or None)

# ------- Handler per /nft_chart -------
async def nft_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler per il comando /nft_chart.
    Formato: /nft_chart <slug> <field>
    Esempio: /nft_chart bored-ape-yacht-club native
    """
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    # Verifica parametri
    if len(context.args) < 2:
        await update.message.reply_text(
            "Formato corretto: /nft_chart <slug> <field>\n"
            "Esempio: /nft_chart bored-ape-yacht-club native\n"
            "Field: 'native' o 'usd'",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    slug = context.args[0].lower()
    field = context.args[1].lower()
    if field not in ["native", "usd"]:
        await update.message.reply_text(
            "Field non valido. Usa 'native' o 'usd'.",
            reply_markup=ReplyKeyboardRemove()
        )
        return
    
    db_field = "floor_native" if field == "native" else "floor_usd"
    
    # Recupera collection_identifier e chain
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT collection_identifier, chain FROM nft_collections WHERE slug = ?",
        (slug,)
    )
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug non trovato.")
        conn.close()
        return
    collection_identifier, chain = row
    
    # Recupera dati storici degli ultimi 200 giorni
    cur.execute(
        f"""
        SELECT latest_floor_date, {db_field}
        FROM historical_nft_data
        WHERE collection_identifier = ? AND latest_floor_date >= date('now', '-200 days')
        ORDER BY latest_floor_date ASC
        """,
        (collection_identifier,)
    )
    data = cur.fetchall()
    conn.close()
    
    if not data:
        await update.message.reply_text(
            f"Nessun dato storico trovato per {slug} negli ultimi 200 giorni."
        )
        return
    
    # Genera il grafico
    chart_buffer = create_nft_chart(slug, data, db_field, chain)
    if not chart_buffer:
        await update.message.reply_text(
            f"Errore nella generazione del grafico per {slug}."
        )
        return
    
    # Invia il grafico
    currency_label = chain.upper() if field == "native" else "USD"
    await update.message.reply_photo(
        photo=chart_buffer,
        caption=f"Grafico del Floor Price ({currency_label}) e Medie Mobili per {slug} (ultimi 200 giorni)",
        reply_markup=ReplyKeyboardRemove()
    )


# ------- /check_daily_insert HANDLER -------
async def check_daily_insert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM historical_nft_data WHERE latest_floor_date = DATE('now')")
    result = cur.fetchone()
    conn.close()

    x = result[0] if result else 0
    await update.message.reply_text(f"{x} record inseriti in data odierna")

# ------- /slug_list_by_prefix HANDLER -------
async def slug_list_by_prefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    if not context.args or len(context.args[0]) < 1:
        await update.message.reply_text("Formato corretto: /slug_list_by_prefix {lettera}")
        return
    letter = context.args[0][0]
    query = "SELECT slug FROM nft_collections WHERE slug LIKE ? COLLATE NOCASE"
    await paginated_list_handler(
        update,
        context,
        query,
        f"{letter}%",
        "slug_list_by_prefix",
        page=0,
        field="slug"
    )

# ------- /slug_list_by_chain HANDLER -------
async def slug_list_by_chain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    if not context.args:
        await update.message.reply_text("Formato corretto: /slug_list_by_chain {chain}")
        return
    chain = context.args[0]
    query = "SELECT slug FROM nft_collections WHERE chain LIKE ? COLLATE NOCASE"
    await paginated_list_handler(
        update,
        context,
        query,
        chain,
        "slug_list_by_chain",
        page=0,
        field="slug"
    )

# ------- /slug_list_by_category HANDLER -------
async def slug_list_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    if not context.args:
        await update.message.reply_text("Formato corretto: /slug_list_by_category {category}")
        return
    category = context.args[0]
    query = "SELECT slug FROM nft_collections WHERE categories LIKE ? COLLATE NOCASE"
    await paginated_list_handler(
        update,
        context,
        query,
        category,
        "slug_list_by_category",
        page=0,
        field="slug"
    )

# ------- Callback handler per paginazione -------
async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    data = update.callback_query.data
    try:
        command, query_value, page = data.split("|")
        page = int(page)
    except Exception:
        await update.callback_query.answer("Errore nei dati di paginazione.", show_alert=True)
        return

    if command == "slug_list_by_prefix":
        query = "SELECT slug FROM nft_collections WHERE slug LIKE ? COLLATE NOCASE"
        await paginated_list_handler(
            update,
            context,
            query,
            query_value,
            command,
            page=page,
            field="slug"
        )
    elif command == "slug_list_by_chain":
        query = "SELECT slug FROM nft_collections WHERE chain LIKE ? COLLATE NOCASE"
        await paginated_list_handler(
            update,
            context,
            query,
            query_value,
            command,
            page=page,
            field="slug"
        )
    elif command == "slug_list_by_category":
        query = "SELECT slug FROM nft_collections WHERE categories LIKE ? COLLATE NOCASE"
        await paginated_list_handler(
            update,
            context,
            query,
            query_value,
            command,
            page=page,
            field="slug"
        )

# ------- /meta HANDLER MIGLIORATO -------
async def meta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    if not context.args:
        await update.message.reply_text("Formato corretto: /meta {slug}")
        return
    slug = context.args[0]

    query = """
        SELECT nc.slug, nc.name, nc.chain, nc.categories, hnd.best_price_url, hnd.latest_floor_date
        FROM nft_collections nc
        INNER JOIN historical_nft_data hnd
        ON nc.collection_identifier = hnd.collection_identifier
        WHERE nc.slug = ? COLLATE NOCASE
    """

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, (slug,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("No results found.")
        return

    # Prendi la riga col latest_floor_date più recente
    latest_row = max(rows, key=lambda row: row[5] if row[5] is not None else "")
    slug_val, name_val, chain_val, categories_val, best_price_url, latest_floor_date = latest_row

    msg = (
        f"🐌 Slug: {slug_val}\n"
        f"🏷️ Name: {name_val}\n"
        f"🔗 Chain: {chain_val}\n"
        f"📂 Categories: {categories_val}\n"
        f"🔗 {best_price_url}\n\n"
        f"🔄 Updated to {latest_floor_date}"
    )
    await update.message.reply_text(msg)

# ---- HANDLER GENERICO SMA (usato sia da /ma_native che da /ma_usd) ----
async def ma_generic(update: Update, context: ContextTypes.DEFAULT_TYPE, floor_field: str):
    """
    Handler generico che calcola le medie mobili semplici.
    Prende come argomento il campo (floor_native o floor_usd) su cui calcolare le SMA.
    """
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    # Verifica che lo slug sia passato come parametro
    if not context.args:
        await update.message.reply_text("Uso: /ma_native <slug> oppure /ma_usd <slug>")
        return
    slug = context.args[0]
    conn = get_db_connection()
    cur = conn.cursor()
    # Recupera collection_identifier
    cur.execute("SELECT collection_identifier FROM nft_collections WHERE slug=?", (slug,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug not found")
        conn.close()
        return
    collection_identifier = row[0]
    # Conta record storici disponibili
    cur.execute("SELECT COUNT(*) FROM historical_nft_data WHERE collection_identifier=?", (collection_identifier,))
    collection_historical_count = cur.fetchone()[0]
    if collection_historical_count == 0:
        await update.message.reply_text("No historical data found for this slug")
        conn.close()
        return
    # Query delle serie storiche (floor_native o floor_usd)
    cur.execute(f"""
        SELECT latest_floor_date, {floor_field}, chain
        FROM historical_nft_data
        WHERE collection_identifier=?
        ORDER BY latest_floor_date ASC
    """, (collection_identifier,))
    db_rows = cur.fetchall()
    conn.close()
    # Prima data e chain disponibili
    first_available_date = db_rows[0][0]
    slug_chain = db_rows[0][2]
    # Lista delle tuple (data, valore floor selezionato)
    date_value_list = [(r[0], r[1]) for r in db_rows]
    today = datetime.utcnow().date()
    end_date = today.strftime("%Y-%m-%d")
    # Definizione delle medie mobili e soglie giorni mancanti
    periods = [
        (20, 1, "SMA20"),
        (50, 3, "SMA50"),
        (100, 5, "SMA100"),
        (200, 10, "SMA200"),
    ]
    sma_results = {}
    for period, threshold, label in periods:
        value = calculate_sma(
            date_value_list,
            period,
            end_date,
            missing_threshold=threshold
        )
        sma_results[label] = value
    # Calcolo giorni presenti/mancanti per la finestra di 200 giorni
    present, missing = count_days_present(date_value_list, 200, end_date)
    # Output formattato
    msg_out = (
        f"{slug} : {slug_chain}, {collection_historical_count} records found\n\n"
        f"📅 Data available since: {first_available_date}\n\n"
        f"SMA20: {sma_results['SMA20']}\n"
        f"SMA50: {sma_results['SMA50']}\n"
        f"SMA100: {sma_results['SMA100']}\n"
        f"SMA200: {sma_results['SMA200']}\n\n"
        f"Days check: {present} present, {missing} missing"
    )
    await update.message.reply_text(msg_out)
# ---- HANDLER SPECIFICI ----
async def ma_native(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /ma_native, calcola SMA sui valori floor_native"""
    await ma_generic(update, context, floor_field="floor_native")
async def ma_usd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler per /ma_usd, calcola SMA sui valori floor_usd"""
    await ma_generic(update, context, floor_field="floor_usd")

# ------- MAIN -------
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_daily_insert", check_daily_insert))
    application.add_handler(CommandHandler("slug_list_by_prefix", slug_list_by_prefix))
    application.add_handler(CommandHandler("slug_list_by_chain", slug_list_by_chain))
    application.add_handler(CommandHandler("slug_list_by_category", slug_list_by_category))
    application.add_handler(CommandHandler("meta", meta))
    application.add_handler(CommandHandler("ma_native", ma_native))
    application.add_handler(CommandHandler("ma_usd", ma_usd))
    application.add_handler(CommandHandler("nft_chart", nft_chart))
    application.add_handler(CallbackQueryHandler(pagination_callback))
    # Registra i comandi autocomplete per popup "/"
    application.bot.set_my_commands(COMMANDS)
    print("Bot Telegram avviato.")
    application.run_polling()

if __name__ == "__main__":
    main()

