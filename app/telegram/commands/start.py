from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    await update.message.reply_text(
        "Welcome or Welcome Back! :)\n\n"
        "With this bot, you can:\n"
        "🔍 Search for NFT collections by chain, category, or prefix.\n"
        "ℹ️ View the metadata of a slug.\n"
        "📈 Check the various moving averages of a collection.\n\n"
        "CEO: Ser Basato 💀\n"
        "CTO: Ser Muay Thai 🥊 🇹🇭\n"
        "© All rights reserved\n",
        reply_markup=ReplyKeyboardRemove()
    )

start_handler = CommandHandler("start", start)