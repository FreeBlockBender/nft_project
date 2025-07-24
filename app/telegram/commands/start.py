from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    await update.message.reply_text(
        "Benvenuto o Bentornato! :)\n\n"
        "Con questo bot potrai:\n"
        "🔍 Cercare le collezioni per chain, categoria o prefisso.\n"
        "ℹ️ Visualizzare i metadati di uno slug.\n"
        "📈 Consultare le diverse medie mobili di una collection.\n\n"
        "CEO: Ser Basato 💀\n"
        "CTO: Ser Muay Thai 🥊 🇹🇭\n"
        "© All rights reserved\n",
        reply_markup=ReplyKeyboardRemove()
    )

start_handler = CommandHandler("start", start)