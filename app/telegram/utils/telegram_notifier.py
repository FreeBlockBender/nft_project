import requests
import httpx
from app.config.config import load_config

# Global client to reuse (best practice)
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client

async def send_telegram_message(message: str, chat_id: str):
    """
    Invia un messaggio Telegram in modo asincrono.
    """
    config = load_config()
    token = config.get("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN o chat_id mancante nella config")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",                  # ← you probably want this
        "disable_web_page_preview": True       # ← cleaner messages
    }

    client = _get_client()
    response = await client.post(url, data=payload)
    
    if not response.is_success:
        error_detail = response.text
        raise Exception(f"Errore Telegram API: {response.status_code} - {error_detail}")

    return response.json()  # optional: return the Telegram response

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