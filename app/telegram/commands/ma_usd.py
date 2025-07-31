from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.ma_generic import ma_generic

async def ma_usd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    """Handler per /ma_usd, calcola SMA sui valori floor_usd"""
    await ma_generic(update, context, floor_field="floor_usd")

ma_usd_handler = CommandHandler("ma_usd", ma_usd)