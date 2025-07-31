import logging

async def error_handler(update, context):
    logging.error(f"Errore: {context.error}")
    # Se vuoi: notifica all’utente
    # if update and update.message:
    #     await update.message.reply_text("Si è verificato un errore inatteso.")