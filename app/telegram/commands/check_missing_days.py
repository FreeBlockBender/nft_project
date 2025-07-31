from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.database.db_connection import get_db_connection

async def check_days_presence_since(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    # Verifica parametro data
    if not context.args or len(context.args[0]) != 10:
        await update.message.reply_text("❌ Devi specificare una data nel formato 'YYYY-MM-DD'.")
        return

    arg_date = context.args[0]
    try:
        start_date = datetime.strptime(arg_date, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("❌ Formato data errato. Usa 'YYYY-MM-DD'.")
        return

    today = datetime.utcnow().date()
    if start_date > today:
        await update.message.reply_text("❌ La data indicata è nel futuro.")
        return

    # Query raggruppata per giorni con almeno 1500 record
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT latest_floor_date, COUNT(*)
        FROM historical_nft_data
        WHERE latest_floor_date >= DATE(?)
        GROUP BY latest_floor_date
        HAVING COUNT(*) > 1500
        ORDER BY latest_floor_date ASC
        """,
        (arg_date,)
    )
    results = cur.fetchall()
    conn.close()

    if not results:
        await update.message.reply_text("❌ Nessun dato con più di 1500 record trovato.")
        return

    date_list = [datetime.strptime(row[0], "%Y-%m-%d").date() for row in results]  # elenco date presenti
    # Costruisci la lista di tutti i giorni tra start_date e ultimo giorno trovato
    all_dates = [start_date + timedelta(days=x) for x in range((date_list[-1] - start_date).days + 1)]
    missing = [d.strftime("%Y-%m-%d") for d in all_dates if d not in date_list]

    # Risposta
    if not missing:
        await update.message.reply_text("✅ Non ci sono giorni mancanti nella serie dati.")
    else:
        msg = "❌ Giorni mancanti:\n" + "\n".join(missing)
        await update.message.reply_text(msg)

check_missing_days_handler = CommandHandler("check_missing_days", check_days_presence_since)