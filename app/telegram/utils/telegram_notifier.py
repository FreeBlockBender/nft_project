import requests
from app.config.config import load_config

def send_telegram_message(message: str, chat_id: str):
    """
    Invia un messaggio Telegram al chat_id indicato.
    Usa il bot token dalla configurazione.
    """
    config = load_config()
    token = config.get("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        raise ValueError("TOKEN o chat_id mancante")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message
    }
    response = requests.post(url, data=payload)
    if not response.ok:
        raise Exception(f"Errore Telegram: {response.text}")

def get_monitoring_chat_id():
    """
    Restituisce il chat_id per la supervisione/monitoraggio dal file .env
    """
    config = load_config()
    return config.get("TELEGRAM_MONITORING_CHAT_ID", "")

def get_channel_chat_id():
    """
    Restituisce il chat_id per la pubblicazione sul canale Telegram dal file .env
    """
    config = load_config()
    return config.get("TELEGRAM_CHANNEL_CHAT_ID", "")

def get_gc_draft_chat_id():
    """
    Restituisce il chat_id per i draft sulle golden cross, pre invio sul canale
    """
    config = load_config()
    return config.get("TELEGRAM_GC_DRAFT_CHAT_ID", "")