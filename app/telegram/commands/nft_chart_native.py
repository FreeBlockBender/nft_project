from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ConversationHandler, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from datetime import datetime
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.chart import create_nft_chart
from app.database.db_connection import get_db_connection

SELECT_DAYS, ENTER_SLUG = range(2)

async def start_chart_native(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END

    context.user_data["command"] = "nft_chart_native"
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
        "Choose the time range for the chart display (native):", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_DAYS

async def select_days_native(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["days"] = int(query.data)
    await query.edit_message_text("Insert the slug of the NFT collection:")
    return ENTER_SLUG

async def enter_slug_native(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
        "SELECT latest_floor_date, floor_native, chain_currency_symbol FROM historical_nft_data "
        "WHERE slug = ? AND latest_floor_date >= date('now', ? || ' days') "
        "ORDER BY latest_floor_date ASC",
        (slug , -days)
    )
    data = cur.fetchall()
    chain_currency_symbol = next((r[2] for r in data if r[2]), None)
    conn.close()

    if not data:
        await update.message.reply_text(f"No data available for {slug} in the last {days} days.")
        return ConversationHandler.END

    if len(data) < days:
        await update.message.reply_text(f"Warning: Only {len(data)} days of data available, less than the {days} days requested.")

    chart = create_nft_chart(slug, data, "floor_native", chain, days, chain_currency_symbol)
    if not chart:
        await update.message.reply_text("Error in generating the chart.")
        return ConversationHandler.END

    currency = chain_currency_symbol or chain.upper()
    await update.message.reply_photo(
        photo=chart,
        caption=f"Floor Price Chart ({currency}) - {slug} - Last {days} days",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

nft_chart_native_handler = ConversationHandler(
    entry_points=[CommandHandler("nft_chart_native", start_chart_native)],
    states={
        SELECT_DAYS: [CallbackQueryHandler(select_days_native)],
        ENTER_SLUG: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slug_native)],
    },
    fallbacks=[]
)
