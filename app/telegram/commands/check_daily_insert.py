from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.database.db_connection import get_db_connection
from datetime import datetime

async def check_daily_insert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    # Se viene passato un argomento, validalo come data
    if context.args and len(context.args) > 0:
        arg_date = context.args[0]
        try:
            # Tenta di parsare la data
            datetime.strptime(arg_date, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "❌ Formato data errato. Inserisci la data nel formato 'YYYY-MM-DD'."
            )
            return
        query_date = arg_date
    else:
        # Nessun argomento: usa oggi
        query_date = "now"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM historical_nft_data WHERE latest_floor_date = DATE(?)",
        (query_date,)
    )
    result = cur.fetchone()
    conn.close()
    x = result[0] if result else 0
    msg = (
        f"{x} inserted records today" if query_date == "now"
        else f"{x} inserted records in date: {query_date}"
    )
    await update.message.reply_text(msg)

check_daily_insert_handler = CommandHandler("check_daily_insert", check_daily_insert)