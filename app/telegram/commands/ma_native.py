from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.ma_generic import ma_generic

async def ma_native(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    """Handler per /ma_native, calcola SMA sui valori floor_native"""
    await ma_generic(update, context, floor_field="floor_native")

ma_native_handler = CommandHandler("ma_native", ma_native)