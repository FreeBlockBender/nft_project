from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.database.db_connection import get_db_connection

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

meta_handler = CommandHandler("meta", meta)