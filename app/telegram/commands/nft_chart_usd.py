from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ConversationHandler, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from datetime import datetime
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.chart import create_nft_chart
from app.database.db_connection import get_db_connection

SELECT_DAYS_USD, ENTER_SLUG_USD = range(2)

async def start_chart_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END

    context.user_data["command"] = "nft_chart_usd"
    keyboard = [
        [InlineKeyboardButton("7D", callback_data="7")],
        [InlineKeyboardButton("1M", callback_data="30")],
        [InlineKeyboardButton("3M", callback_data="90")],
        [InlineKeyboardButton("6M", callback_data="180")],
        [InlineKeyboardButton("1Y", callback_data="365")],
        [InlineKeyboardButton("2Y", callback_data="730")],
        [InlineKeyboardButton("3Y", callback_data="1095")],
    ]
    await update.message.reply_text(
        "Choose the time range for the chart display (USD):", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_DAYS_USD

async def select_days_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["days"] = int(query.data)
    await query.edit_message_text("Insert the slug of the NFT collection:")
    return ENTER_SLUG_USD

async def enter_slug_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    slug = update.message.text.lower()
    days = context.user_data.get("days")
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier, chain FROM nft_collections WHERE slug = ?", (slug,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug not found.")
        conn.close()
        return ConversationHandler.END
    collection_identifier, chain = row

    cur.execute(
        "SELECT latest_floor_date, floor_usd FROM historical_nft_data "
        "WHERE collection_identifier IN (?,?) AND latest_floor_date >= date('now', ? || ' days') "
        "ORDER BY latest_floor_date ASC",
        (collection_identifier, slug.replace('-',''), -days)
    )
    data = cur.fetchall()
    conn.close()

    if not data:
        await update.message.reply_text(f"No data available for {slug} in the last {days} days.")
        return ConversationHandler.END

    if len(data) < days:
        await update.message.reply_text(f"Warning: Only {len(data)} days of data available, less than the {days} days requested.")

    chart = create_nft_chart(slug, data, "floor_usd", chain, days)
    if not chart:
        await update.message.reply_text("Error in generating the chart.")
        return ConversationHandler.END

    await update.message.reply_photo(
        photo=chart,
        caption=f"Floor Price Chart (USD) - {slug} - Last {days} days",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

nft_chart_usd_handler = ConversationHandler(
    entry_points=[CommandHandler("nft_chart_usd", start_chart_usd)],
    states={
        SELECT_DAYS_USD: [CallbackQueryHandler(select_days_usd)],
        ENTER_SLUG_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slug_usd)],
    },
    fallbacks=[]
)
