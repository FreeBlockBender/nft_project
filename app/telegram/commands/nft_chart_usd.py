from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import (
    ConversationHandler, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.chart import create_nft_chart

SELECT_DAYS_USD, ENTER_SLUG_USD = range(2)

async def start_chart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("7", callback_data="7"), InlineKeyboardButton("30", callback_data="30")],
        [InlineKeyboardButton("90", callback_data="90"), InlineKeyboardButton("180", callback_data="180")],
        [InlineKeyboardButton("365", callback_data="365")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Quanti giorni vuoi visualizzare nel grafico (prezzo USD)?", 
        reply_markup=reply_markup
    )
    return SELECT_DAYS_USD

async def select_days_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["days"] = int(query.data)
    await query.edit_message_text("Inserisci lo slug della collezione NFT:")
    return ENTER_SLUG_USD

async def enter_slug_usd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    slug = update.message.text
    days = context.user_data.get("days")
    user_id = update.effective_user.id
    if not (slug and days):
        await update.message.reply_text("Errore: dati mancanti.")
        return ConversationHandler.END

    result = create_nft_chart(slug, days=days, mode="usd")
    if result and result.get("status") == "success":
        with open(result["filepath"], "rb") as chart_file:
            await update.message.reply_photo(chat_id=update.effective_chat.id, photo=InputFile(chart_file))
    else:
        await update.message.reply_text("Errore nella generazione del grafico (USD).")
    return ConversationHandler.END

usd_chart_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("nft_chart_usd", start_chart)],
    states={
        SELECT_DAYS_USD: [CallbackQueryHandler(select_days_usd)],
        ENTER_SLUG_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slug_usd)],
    },
    fallbacks=[]
)