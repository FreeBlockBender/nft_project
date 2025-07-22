"""
Entrypoint principale del bot Telegram: importa e registra tutti i command handler.
"""

from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ConversationHandler
)
from app.telegram.commands.start import start_handler
from app.telegram.commands.nft_chart_native import native_chart_conv_handler
from app.telegram.commands.nft_chart_usd import usd_chart_conv_handler
from app.telegram.commands.check_daily_insert import check_daily_insert_handler
from app.telegram.commands.check_missing_days import check_missing_days_handler
from app.telegram.commands.slug_list_by_prefix import slug_list_by_prefix_handler
from app.telegram.commands.slug_list_by_chain import slug_list_by_chain_handler
from app.telegram.commands.slug_list_by_category import slug_list_by_category_handler
from app.telegram.commands.meta import meta_handler
from app.telegram.commands.ma_native import ma_native_handler
from app.telegram.commands.ma_usd import ma_usd_handler
from app.telegram.utils.pagination import pagination_callback_handler
from app.telegram.utils.error_handler import error_handler

# Carica il token dal modulo di configurazione
from app.config import load_config

def main():
    config = load_config()
    bot_token = config["TELEGRAM_BOT_TOKEN"]

    # Inizializza l'applicazione Telegram
    application = Application.builder().token(bot_token).build()

    # Registrazione di tutti gli handler di comando e callback
    application.add_handler(start_handler)
    application.add_handler(native_chart_conv_handler)
    application.add_handler(usd_chart_conv_handler)
    application.add_handler(check_daily_insert_handler)
    application.add_handler(check_missing_days_handler)
    application.add_handler(slug_list_by_prefix_handler)
    application.add_handler(slug_list_by_chain_handler)
    application.add_handler(slug_list_by_category_handler)
    application.add_handler(meta_handler)
    application.add_handler(ma_native_handler)
    application.add_handler(ma_usd_handler)
    application.add_handler(pagination_callback_handler)
    application.add_error_handler(error_handler)

    print("Bot Telegram avviato. In ascolto di comandi...")
    application.run_polling()

if __name__ == "__main__":
    main()