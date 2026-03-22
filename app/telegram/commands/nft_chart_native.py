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

SELECT_DAYS, ENTER_SLUG = range(2)

async def start_chart_native(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    logger.info(f"[nft_chart_native] Command started by user {user_id}")
    if not is_authorized(user_id):
        logger.warning(f"[nft_chart_native] User {user_id} not authorized")
        await access_denied(update)
        return ConversationHandler.END

    context.user_data["command"] = "nft_chart_native"
    logger.debug(f"[nft_chart_native] Showing time range selection keyboard to user {user_id}")
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
    days = int(query.data)
    user_id = update.effective_user.id
    logger.debug(f"[nft_chart_native] User {user_id} selected {days} days")
    await query.answer()
    context.user_data["days"] = days
    await query.edit_message_text("Insert the slug of the NFT collection:")
    return ENTER_SLUG

async def enter_slug_native(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    slug = update.message.text.lower()
    days = context.user_data.get("days")
    user_id = update.effective_user.id
    logger.info(f"[nft_chart_native] User {user_id} requested chart for slug: {slug}, days: {days}")
    
    if not is_authorized(user_id):
        logger.warning(f"[nft_chart_native] User {user_id} not authorized at slug entry")
        await access_denied(update)
        return ConversationHandler.END

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        logger.debug(f"[nft_chart_native] Querying nft_collections by slug: {slug}")
        
        cur.execute(
            "SELECT c.collection_identifier, c.chain, c.chain_currency_symbol "
            "FROM nft_collections c "
            "LEFT JOIN historical_nft_data h ON h.collection_identifier = c.collection_identifier "
            "WHERE c.slug = ? "
            "GROUP BY c.collection_identifier, c.chain, c.chain_currency_symbol "
            "ORDER BY MAX(h.latest_floor_date) DESC "
            "LIMIT 1",
            (slug,)
        )
        row = cur.fetchone()
        
        if not row:
            logger.warning(f"[nft_chart_native] Slug '{slug}' not found in nft_collections")
            await update.message.reply_text("Slug not found.")
            conn.close()
            return ConversationHandler.END
        
        collection_identifier, chain, chain_currency_symbol = row
        logger.debug(f"[nft_chart_native] Found collection: {collection_identifier}, chain: {chain}")

        logger.debug(f"[nft_chart_native] Querying historical_nft_data for {collection_identifier}, last {days} days")
        cur.execute(
            "SELECT latest_floor_date, floor_native FROM historical_nft_data "
            "WHERE collection_identifier = ? AND latest_floor_date >= date('now', ? || ' days') "
            "ORDER BY latest_floor_date ASC",
            (collection_identifier, -days)
        )
        data = cur.fetchall()
        conn.close()
        
        logger.info(f"[nft_chart_native] Retrieved {len(data)} data points for {slug} in {days} days")

        if not data:
            logger.warning(f"[nft_chart_native] No data available for {slug} in the last {days} days")
            await update.message.reply_text(f"No data available for {slug} in the last {days} days.")
            return ConversationHandler.END

        if len(data) < days:
            logger.warning(f"[nft_chart_native] Only {len(data)} days available (requested {days})")
            await update.message.reply_text(f"Warning: Only {len(data)} days of data available, less than the {days} days requested.")

        logger.debug(f"[nft_chart_native] Generating chart for {slug}")
        chart = create_nft_chart(slug, data, "floor_native", chain, days, chain_currency_symbol=chain_currency_symbol)
        
        if not chart:
            logger.error(f"[nft_chart_native] Chart generation failed for {slug}")
            await update.message.reply_text("Error in generating the chart.")
            return ConversationHandler.END

        currency = chain.upper()
        logger.debug(f"[nft_chart_native] Sending chart to user {user_id}")
        await update.message.reply_photo(
            photo=chart,
            caption=f"Floor Price Chart ({currency}) - {slug} - Last {days} days",
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"[nft_chart_native] Chart sent successfully to user {user_id}")
        return ConversationHandler.END
    
    except Exception as e:
        logger.error(f"[nft_chart_native] Exception occurred for user {user_id}, slug {slug}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"An error occurred: {str(e)}")
        return ConversationHandler.END

nft_chart_native_handler = ConversationHandler(
    entry_points=[CommandHandler("nft_chart_native", start_chart_native)],
    states={
        SELECT_DAYS: [CallbackQueryHandler(select_days_native)],
        ENTER_SLUG: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slug_native)],
    },
    fallbacks=[]
)
