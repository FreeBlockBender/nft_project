from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.pagination import get_paginated_results, build_pagination_keyboard, paginated_list_handler
from app.database.db_connection import get_db_connection

PAGE_SIZE = 10

async def slug_list_by_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    if not context.args:
        await update.message.reply_text("Formato corretto: /slug_list_by_category {category}")
        return
    category = context.args[0]
    query = "SELECT slug FROM nft_collections WHERE categories LIKE ? COLLATE NOCASE"
    await paginated_list_handler(update, context, query, category, "slug_list_by_category")

slug_list_by_category_handler = CommandHandler("slug_list_by_category", slug_list_by_category)