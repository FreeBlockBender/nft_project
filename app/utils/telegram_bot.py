import os
import logging
import sqlite3
import numpy as np
import matplotlib.pyplot as plt
import io
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
    ConversationHandler,
    MessageHandler,
)
from telegram.constants import ParseMode
from scipy.interpolate import interp1d

from app.utils.moving_average import calculate_sma, count_days_present

# ------- Stati della conversazione -------
SELECT_DAYS, ENTER_SLUG = range(2)

# ------- Configurazione iniziale -------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "nft_data.sqlite3")
ALLOWED_TELEGRAM_IDS = set(
    int(x.strip()) for x in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",") if x.strip()
)

# ------- Comandi autocomplete con descrizione -------
COMMANDS = [
    BotCommand("start", "Mostra messaggio di benvenuto"),
    BotCommand("slug_list_by_prefix", "Lista slug che iniziano con una lettera"),
    BotCommand("slug_list_by_chain", "Lista slug filtrati per chain"),
    BotCommand("slug_list_by_category", "Lista slug filtrati per categoria"),
    BotCommand("meta", "Mostra i metadati di una collezione NFT"),
    BotCommand("ma", "Analisi floor price e medie mobili"),
    BotCommand("nft_chart_native", "Mostra il grafico del floor price (native) con medie mobili"),
    BotCommand("nft_chart_usd", "Mostra il grafico del floor price (USD) con medie mobili"),
]

# ------- Logging -------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------- Helper autorizzazione -------
def is_authorized(user_id: int) -> bool:
    return user_id in ALLOWED_TELEGRAM_IDS

async def access_denied(update: Update):
    if update.message:
        await update.message.reply_text("Access denied", reply_markup=ReplyKeyboardRemove())
    elif update.callback_query:
        await update.callback_query.answer("Access denied", show_alert=True)

# ------- Connessione DB -------
def get_db_connection():
    return sqlite3.connect(DB_PATH)

# ------- Funzione per generare il grafico dei floor price e SMA -------
def create_nft_chart(slug: str, data: list, field: str, chain: str, days: int, chain_currency_symbol: str = None):
    """
    Genera un grafico dei floor price e delle medie mobili per una collezione NFT.
    
    Args:
        slug (str): Slug della collezione NFT.
        data (list): Lista di tuple (data, floor_price) dalla tabella historical_nft_data.
        field (str): Campo da plottare ('floor_native' o 'floor_usd').
        chain (str): Chain della collezione (per il titolo e l'etichetta).
        days (int): Numero di giorni da visualizzare.
        chain_currency_symbol (str, optional): Simbolo della valuta nativa della chain (es. ETH, BNB).
    
    Returns:
        BytesIO: Buffer contenente l'immagine del grafico in formato PNG.
    """
    if not data:
        return None
    
    # Estrai date e valori, convertendo None o non numerici in np.nan
    dates = [datetime.strptime(row[0], "%Y-%m-%d") for row in data]
    values = []
    for row in data:
        value = row[1]
        if value is None or not (isinstance(value, (int, float)) or str(value).replace('.', '').replace('-', '').isdigit()):
            values.append(np.nan)
        else:
            values.append(float(value))
    
    if all(np.isnan(values)):
        return None
    
    # Crea una serie temporale continua
    date_nums = np.array([d.timestamp() for d in dates])
    value_nums = np.array(values, dtype=np.float64)
    date_min = min(dates)
    date_max = max(dates)
    date_range = np.linspace(date_min.timestamp(), date_max.timestamp(), max(10, len(dates)))
    interp_func = interp1d(date_nums, value_nums, kind='linear', fill_value="extrapolate")
    interp_values = interp_func(date_range)
    interp_dates = [datetime.fromtimestamp(ts) for ts in date_range]
    
    # Definisci le medie mobili in base al numero di giorni
    date_value_list = [(d.strftime("%Y-%m-%d"), v) for d, v in zip(dates, values)]
    end_date = date_max.strftime("%Y-%m-%d")
    periods = []
    if days >= 7:  # 7 days or more: show floor price
        pass  # Floor price is always shown
    if days >= 30:  # 1 month
        periods.append((20, 1, "SMA20"))
    if days >= 90:  # 3 months
        periods.append((50, 3, "SMA50"))
    if days >= 180:  # 6 months or 1 year
        periods.extend([(100, 5, "SMA100"), (200, 10, "SMA200")])
    
    sma_data = {}
    for period, threshold, label in periods:
        sma_values = []
        for i in range(len(interp_dates)):
            window_end = interp_dates[i].strftime("%Y-%m-%d")
            sma = calculate_sma(date_value_list, period, window_end, missing_threshold=threshold)
            sma_values.append(sma if not np.isnan(sma) else np.nan)
        sma_nums = np.array(sma_values)
        sma_interp = interp1d(np.arange(len(sma_nums)), sma_nums, kind='linear', fill_value="extrapolate")
        sma_data[label] = sma_interp(np.linspace(0, len(sma_nums)-1, len(interp_dates)))
        print(f"{label} values: {sma_values[:10]}...")  # Debug
    
    # Imposta uno stile crypto-friendly con tema dark e floor price in blu
    plt.style.use('dark_background')  # Tema scuro
    plt.figure(figsize=(12, 6), facecolor='#1E1E1E')  # Sfondo nero
    ax = plt.gca()
    ax.set_facecolor('#2B2B2B')  # Sfondo dell'asse
    
    # Plot del floor price in blu
    plt.plot(interp_dates, interp_values, label=f"Floor Price ({field})", color="#3B82F6", linewidth=2, marker='o', markersize=4)
    
    # Plot delle medie mobili come linee continue
    colors = {"SMA20": "#F97316", "SMA50": "#34D399", "SMA100": "#F87171", "SMA200": "#A855F7"}
    for label, sma_values in sma_data.items():
        plt.plot(interp_dates, sma_values, label=label, color=colors[label], linewidth=1.5)
    
    # Personalizza gli assi e la griglia
    plt.title(f"📈 Floor Price e Medie Mobili per {slug} ({chain}) - {days} giorni", color="white")
    plt.xlabel("Data", color="white")
    # Usa chain_currency_symbol per nft_chart_native, altrimenti USD
    y_label = f"Prezzo ({chain_currency_symbol if field == 'floor_native' and chain_currency_symbol else chain.upper() if field == 'floor_native' else 'USD'})"
    plt.ylabel(y_label, color="white")
    plt.grid(True, color="#4B5563", linestyle='--', alpha=0.5)  # Griglia leggera
    plt.xticks(rotation=45, color="white")
    plt.yticks(color="white")
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False, facecolor='#2B2B2B', edgecolor='#2B2B2B', labelcolor='white')
    
    # Ottimizza il layout
    plt.tight_layout()
    
    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", bbox_inches="tight", facecolor='#1E1E1E')
    buffer.seek(0)
    plt.close()
    return buffer


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
        keyboard.append(InlineKeyboardButton("⬅️", callback_data=f"{command}|{query_value}|{page-1}"))
    if page < (total_pages - 1):
        keyboard.append(InlineKeyboardButton("➡️", callback_data=f"{command}|{query_value}|{page+1}"))
    return InlineKeyboardMarkup([keyboard]) if keyboard else None

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
    text = "No results found." if not page_results else f"Risultati (pagina {page+1}/{total_pages}):\n" + "\n".join(page_results)
    reply_markup = build_pagination_keyboard(command, query_value, page, total_pages)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup or ReplyKeyboardRemove())
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

# ------- Handler per /nft_chart_native e /nft_chart_usd -------
async def start_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inizia la conversazione chiedendo il range di giorni."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END
    
    # Store the command in context.user_data
    context.user_data["command"] = update.message.text  # e.g., "/nft_chart_native" or "/nft_chart_usd"
    keyboard = [
        [InlineKeyboardButton("7 days", callback_data="7")],
        [InlineKeyboardButton("1 month", callback_data="30")],
        [InlineKeyboardButton("3 months", callback_data="90")],
        [InlineKeyboardButton("6 months", callback_data="180")],
        [InlineKeyboardButton("1 year", callback_data="365")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Seleziona il range di giorni per il grafico:", reply_markup=reply_markup)
    return SELECT_DAYS

async def select_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gestisce la selezione dei giorni e chiede lo slug."""
    query = update.callback_query
    await query.answer()
    context.user_data["days"] = int(query.data)
    await query.edit_message_text(f"Hai selezionato {query.data} giorni. Inserisci lo slug della collezione NFT:")
    return ENTER_SLUG

async def enter_slug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gestisce l'input dello slug e genera il grafico."""
    user_id = update.message.from_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END
    
    slug = update.message.text.lower()
    days = context.user_data["days"]
    command = context.user_data.get("command", "").lower()
    
    # Determine field based on the command
    field = "floor_native" if "nft_chart_native" in command else "floor_usd"
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier, chain FROM nft_collections WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug non trovato.")
        conn.close()
        return ConversationHandler.END
    collection_identifier, chain = row
    
    # Fetch data including chain_currency_symbol
    cur.execute(
        f"SELECT latest_floor_date, {field}, chain_currency_symbol FROM historical_nft_data "
        "WHERE collection_identifier = ? AND latest_floor_date >= date('now', ? || ' days') "
        "ORDER BY latest_floor_date ASC",
        (collection_identifier, -days)
    )
    data = cur.fetchall()
    # Extract the first non-None chain_currency_symbol (assuming it’s consistent)
    chain_currency_symbol = next((row[2] for row in data if row[2] is not None), None)
    conn.close()
    
    if not data:
        await update.message.reply_text(f"Nessun dato storico trovato per {slug} negli ultimi {days} giorni.")
        return ConversationHandler.END
    if len(data) < days:
        await update.message.reply_text(f"Attenzione: Solo {len(data)} giorni di dati disponibili, meno dei {days} giorni richiesti.")
    
    chart_buffer = create_nft_chart(slug, data, field, chain, days, chain_currency_symbol)
    if not chart_buffer:
        await update.message.reply_text(f"Errore nella generazione del grafico per {slug}.")
        return ConversationHandler.END
    
    currency_label = chain_currency_symbol if field == "floor_native" and chain_currency_symbol else chain.upper() if field == "floor_native" else "USD"
    await update.message.reply_photo(
        photo=chart_buffer,
        caption=f"Grafico del Floor Price ({currency_label}) e Medie Mobili per {slug} (ultimi {days} giorni)",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

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
    await paginated_list_handler(update, context, query, f"{letter}%", "slug_list_by_prefix")

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
    await paginated_list_handler(update, context, query, chain, "slug_list_by_chain")

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
    await paginated_list_handler(update, context, query, category, "slug_list_by_category")

# ------- Callback handler per paginazione -------
async def pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    try:
        command, query_value, page = update.callback_query.data.split("|")
        page = int(page)
    except Exception:
        await update.callback_query.answer("Errore nei dati di paginazione.", show_alert=True)
        return

    if command == "slug_list_by_prefix":
        query = "SELECT slug FROM nft_collections WHERE slug LIKE ? COLLATE NOCASE"
        await paginated_list_handler(update, context, query, query_value, command, page)
    elif command == "slug_list_by_chain":
        query = "SELECT slug FROM nft_collections WHERE chain LIKE ? COLLATE NOCASE"
        await paginated_list_handler(update, context, query, query_value, command, page)
    elif command == "slug_list_by_category":
        query = "SELECT slug FROM nft_collections WHERE categories LIKE ? COLLATE NOCASE"
        await paginated_list_handler(update, context, query, query_value, command, page)

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
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /ma_native <slug> oppure /ma_usd <slug>")
        return
    slug = context.args[0]
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier FROM nft_collections WHERE slug=?", (slug,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug not found")
        conn.close()
        return
    collection_identifier = row[0]
    
    cur.execute("SELECT COUNT(*) FROM historical_nft_data WHERE collection_identifier=?", (collection_identifier,))
    collection_historical_count = cur.fetchone()[0]
    if collection_historical_count == 0:
        await update.message.reply_text("No historical data found for this slug")
        conn.close()
        return
    
    cur.execute(
        f"SELECT latest_floor_date, {floor_field}, chain FROM historical_nft_data WHERE collection_identifier=? "
        "ORDER BY latest_floor_date ASC",
        (collection_identifier,)
    )
    db_rows = cur.fetchall()
    conn.close()
    
    first_available_date = db_rows[0][0]
    slug_chain = db_rows[0][2]
    date_value_list = [(r[0], r[1]) for r in db_rows]
    today = datetime.utcnow().date()
    end_date = today.strftime("%Y-%m-%d")
    
    periods = [
        (20, 1, "SMA20"),
        (50, 3, "SMA50"),
        (100, 5, "SMA100"),
        (200, 10, "SMA200"),
    ]
    sma_results = {}
    for period, threshold, label in periods:
        value = calculate_sma(date_value_list, period, end_date, missing_threshold=threshold)
        sma_results[label] = value
    
    present, missing = count_days_present(date_value_list, 200, end_date)
    
    # Corrected formatting with ternary operator outside the format specifier
    sma20_text = f"{sma_results['SMA20']:.4f}" if not np.isnan(sma_results['SMA20']) else "N/A"
    sma50_text = f"{sma_results['SMA50']:.4f}" if not np.isnan(sma_results['SMA50']) else "N/A"
    sma100_text = f"{sma_results['SMA100']:.4f}" if not np.isnan(sma_results['SMA100']) else "N/A"
    sma200_text = f"{sma_results['SMA200']:.4f}" if not np.isnan(sma_results['SMA200']) else "N/A"
    
    msg_out = (
        f"{slug} : {slug_chain}, {collection_historical_count} records found\n\n"
        f"📅 Data available since: {first_available_date}\n\n"
        f"SMA20: {sma20_text}\n"
        f"SMA50: {sma50_text}\n"
        f"SMA100: {sma100_text}\n"
        f"SMA200: {sma200_text}\n\n"
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
    
    # Configura i ConversationHandler per nft_chart_native e nft_chart_usd
    conv_handler_native = ConversationHandler(
        entry_points=[CommandHandler("nft_chart_native", start_chart)],
        states={
            SELECT_DAYS: [CallbackQueryHandler(select_days)],
            ENTER_SLUG: [MessageHandler(None, enter_slug)]
        },
        fallbacks=[]
    )
    conv_handler_usd = ConversationHandler(
        entry_points=[CommandHandler("nft_chart_usd", start_chart)],
        states={
            SELECT_DAYS: [CallbackQueryHandler(select_days)],
            ENTER_SLUG: [MessageHandler(None, enter_slug)]
        },
        fallbacks=[]
    )
    
    # Aggiungi gli handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check_daily_insert", check_daily_insert))
    application.add_handler(CommandHandler("slug_list_by_prefix", slug_list_by_prefix))
    application.add_handler(CommandHandler("slug_list_by_chain", slug_list_by_chain))
    application.add_handler(CommandHandler("slug_list_by_category", slug_list_by_category))
    application.add_handler(CommandHandler("meta", meta))
    application.add_handler(CommandHandler("ma_native", ma_native))
    application.add_handler(CommandHandler("ma_usd", ma_usd))
    application.add_handler(conv_handler_native)
    application.add_handler(conv_handler_usd)
    application.add_handler(CallbackQueryHandler(pagination_callback))
    
    # Registra i comandi autocomplete
    application.bot.set_my_commands(COMMANDS)
    
    # Aggiungi handler per gli errori
    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error(f"Si è verificato un errore: {context.error}")
        # Return None explicitly to avoid TypeError
        return None
    
    application.add_error_handler(error_handler)
    
    print("Bot Telegram avviato.")
    application.run_polling()

if __name__ == "__main__":
    main()