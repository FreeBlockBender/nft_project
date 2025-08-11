from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.database.db_connection import get_db_connection
import sqlite3

async def historical_data_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cur = conn.cursor()

    # Funzione di utilità per info tabella
    def get_table_stats(table):
        cur.execute(f"SELECT COUNT(*), MIN(latest_floor_date), MAX(latest_floor_date) FROM {table}")
        count, min_date, max_date = cur.fetchone()
        count = count or 0
        return {
            "count": count,
            "from": min_date or "-",
            "to": max_date or "-"
        }

    stats_main = get_table_stats("historical_nft_data")
    stats_archive = get_table_stats("historical_nft_data_archive")

    total = stats_main["count"] + stats_archive["count"]
    perc_main = round(stats_main["count"] / total * 100, 1) if total else 0.0
    perc_archive = round(stats_archive["count"] / total * 100, 1) if total else 0.0

    msg = (
        f"📊 Historical NFT Data\n\n"
        f"📦 Record totali: {stats_main['count']}\n"
        f"🗓️ Periodo coperto: dal {stats_main['from']} al {stats_main['to']}\n\n"
        f"🗂️ Historical NFT Data Archive\n\n"
        f"📦 Record totali: {stats_archive['count']}\n"
        f"🗓️ Periodo coperto: dal {stats_archive['from']} al {stats_archive['to']}\n\n"
        f"📈 Distribuzione dei record:\n"
        f"- 🟢 historical_nft_data: {perc_main}%\n"
        f"- 🔵 historical_nft_data_archive: {perc_archive}%"
    )

    await update.message.reply_text(msg)
    conn.close()

# EXPORTA handler
historical_data_stats_handler = CommandHandler("historical_data_stats", historical_data_stats)