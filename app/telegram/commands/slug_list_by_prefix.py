from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.pagination import get_paginated_results, build_pagination_keyboard, paginated_list_handler
from app.database.db_connection import get_db_connection

PAGE_SIZE = 10

async def slug_list_by_prefix(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    if not context.args or len(context.args[0]) < 1:
        await update.message.reply_text("Formato corretto: /slug_list_by_prefix <prefisso>")
        return

    prefix = context.args[0]
    query = "SELECT slug FROM nft_collections WHERE slug LIKE ? COLLATE NOCASE"
    await paginated_list_handler(update, context, query, f"{prefix}%", "slug_list_by_prefix")

slug_list_by_prefix_handler = CommandHandler("slug_list_by_prefix", slug_list_by_prefix)