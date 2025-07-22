from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.telegram.utils.auth import is_authorized, access_denied
from app.telegram.utils.telegram_query import (
    get_slugs_by_prefix, get_slugs_by_chain, get_slugs_by_category
)

PAGE_SIZE = 10

def get_paginated_results(results, page, page_size=PAGE_SIZE):
    start = page * page_size
    end = start + page_size
    page_results = results[start:end]
    total_pages = (len(results) - 1) // page_size + 1 if results else 1
    return page_results, total_pages

def build_pagination_keyboard(command, query_value, page, total_pages):
    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("⬅️", callback_data=f"{command}|{query_value}|{page-1}"))
    if page < (total_pages - 1):
        keyboard.append(InlineKeyboardButton("➡️", callback_data=f"{command}|{query_value}|{page+1}"))
    return InlineKeyboardMarkup([keyboard]) if keyboard else None

async def pagination_callback(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return

    try:
        data = update.callback_query.data.split("|")
        command, query_value, page = data[0], data[1], int(data[2])
    except Exception:
        await update.callback_query.answer("Errore nei dati di paginazione.", show_alert=True)
        return

    results = []
    if command == "slug_list_by_prefix":
        results = get_slugs_by_prefix(query_value)
    elif command == "slug_list_by_chain":
        results = get_slugs_by_chain(query_value)
    elif command == "slug_list_by_category":
        results = get_slugs_by_category(query_value)
    else:
        await update.callback_query.answer("Comando di paginazione sconosciuto.", show_alert=True)
        return

    if not results:
        await update.callback_query.edit_message_text("Nessun dato da mostrare.")
        return

    page_results, total_pages = get_paginated_results(results, page, PAGE_SIZE)
    text = "\n".join(r[0] for r in page_results)
    keyboard = build_pagination_keyboard(command, query_value, page, total_pages)
    await update.callback_query.edit_message_text(text, reply_markup=keyboard)

pagination_callback_handler = CallbackQueryHandler(pagination_callback)