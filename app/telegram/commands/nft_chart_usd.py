from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ConversationHandler, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from datetime import datetime
import logging
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.chart import create_nft_chart
from app.database.db_connection import get_db_connection

logger = logging.getLogger(__name__)

SELECT_DAYS_USD, ENTER_SLUG_USD = range(2)

async def start_chart_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    logger.info(f"[nft_chart_usd] Command started by user {user_id}")
    if not is_authorized(user_id):
        logger.warning(f"[nft_chart_usd] User {user_id} not authorized")
        await access_denied(update)
        return ConversationHandler.END

    context.user_data["command"] = "nft_chart_usd"
    logger.debug(f"[nft_chart_usd] Showing time range selection keyboard to user {user_id}")
    keyboard = [
        [InlineKeyboardButton("7D", callback_data="ncu:7")],
        [InlineKeyboardButton("1M", callback_data="ncu:30")],
        [InlineKeyboardButton("3M", callback_data="ncu:90")],
        [InlineKeyboardButton("6M", callback_data="ncu:180")],
        [InlineKeyboardButton("1Y", callback_data="ncu:365")],
        [InlineKeyboardButton("2Y", callback_data="ncu:730")],
        [InlineKeyboardButton("3Y", callback_data="ncu:1095")],
    ]
    await update.message.reply_text(
        "Choose the time range for the chart display (USD):", 
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_DAYS_USD

async def select_days_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    days = int(query.data.split(":", 1)[1])
    user_id = update.effective_user.id
    logger.debug(f"[nft_chart_usd] User {user_id} selected {days} days")
    await query.answer()
    context.user_data["days"] = days
    await query.edit_message_text("Insert the slug of the NFT collection:")
    return ENTER_SLUG_USD

async def enter_slug_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    slug = update.message.text.lower()
    days = context.user_data.get("days")
    user_id = update.effective_user.id
    logger.info(f"[nft_chart_usd] User {user_id} requested chart for slug: {slug}, days: {days}")
    
    if not is_authorized(user_id):
        logger.warning(f"[nft_chart_usd] User {user_id} not authorized at slug entry")
        await access_denied(update)
        return ConversationHandler.END

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        logger.debug(f"[nft_chart_usd] Querying nft_collections for collection_identifier: {slug}")
        
        cur.execute("SELECT collection_identifier, chain FROM nft_collections WHERE collection_identifier = ?", (slug,))
        row = cur.fetchone()
        
        if not row:
            logger.warning(f"[nft_chart_usd] Slug '{slug}' not found in nft_collections")
            await update.message.reply_text("Slug not found.")
            conn.close()
            return ConversationHandler.END
        
        collection_identifier, chain = row
        logger.debug(f"[nft_chart_usd] Found collection: {collection_identifier}, chain: {chain}")

        logger.debug(f"[nft_chart_usd] Querying historical_nft_data for {collection_identifier}, last {days} days")
        cur.execute(
            "SELECT latest_floor_date, floor_price_usd FROM historical_nft_data "
            "WHERE collection_identifier = ? AND latest_floor_date >= date('now', ? || ' days') "
            "ORDER BY latest_floor_date ASC",
            (collection_identifier, -days)
        )
        data = cur.fetchall()
        conn.close()
        
        logger.info(f"[nft_chart_usd] Retrieved {len(data)} data points for {slug} in {days} days")

        if not data:
            logger.warning(f"[nft_chart_usd] No data available for {slug} in the last {days} days")
            await update.message.reply_text(f"No data available for {slug} in the last {days} days.")
            return ConversationHandler.END

        if len(data) < days:
            logger.warning(f"[nft_chart_usd] Only {len(data)} days available (requested {days})")
            await update.message.reply_text(f"Warning: Only {len(data)} days of data available, less than the {days} days requested.")

        logger.debug(f"[nft_chart_usd] Generating chart for {slug}")
        chart = create_nft_chart(slug, data, "floor_price_usd", chain, days)
        
        if not chart:
            logger.error(f"[nft_chart_usd] Chart generation failed for {slug}")
            await update.message.reply_text("Error in generating the chart.")
            return ConversationHandler.END

        logger.debug(f"[nft_chart_usd] Sending chart to user {user_id}")
        await update.message.reply_photo(
            photo=chart,
            caption=f"Floor Price Chart (USD) - {slug} - Last {days} days",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"[nft_chart_usd] Chart sent successfully to user {user_id}")
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"[nft_chart_usd] Exception occurred for user {user_id}, slug {slug}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"An error occurred: {str(e)}")
        return ConversationHandler.END

nft_chart_usd_handler = ConversationHandler(
    entry_points=[CommandHandler("nft_chart_usd", start_chart_usd)],
    states={
        SELECT_DAYS_USD: [CallbackQueryHandler(select_days_usd, pattern=r"^ncu:(7|30|90|180|365|730|1095)$")],
        ENTER_SLUG_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slug_usd)],
    },
    fallbacks=[],
)
