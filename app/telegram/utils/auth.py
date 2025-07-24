"""
Modulo autenticazione bot Telegram (usa .env con il modulo config).
"""
from app.config import load_config

# Prende la configurazione caricando prima le variabili da .env
config = load_config()

def _parse_allowed_ids(raw_ids):
    """
    Data una stringa tipo '12345,67890' restituisce {12345, 67890}
    """
    return set(
        int(x.strip())
        for x in raw_ids.split(",")
        if x.strip().isdigit()
    )

ALLOWED_TELEGRAM_IDS = _parse_allowed_ids(config.get("ALLOWED_TELEGRAM_IDS", ""))

def is_authorized(user_id: int) -> bool:
    """
    Restituisce True se user_id è abilitato tra gli allowed (da config/.env).
    """
    print(f"Controllo user_id={user_id}, allowed={ALLOWED_TELEGRAM_IDS}")  # Debug
    return user_id in ALLOWED_TELEGRAM_IDS

async def access_denied(update):
    """
    Risposta all'utente non abilitato in ogni handler/callback.
    """
    if hasattr(update, "message") and update.message:
        await update.message.reply_text("Non sei autorizzato a usare questo comando.")
    elif hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.answer("Non sei autorizzato.", show_alert=True)