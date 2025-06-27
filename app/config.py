from dotenv import load_dotenv
import os

def load_config():
    """
    Carica e restituisce tutte le variabili di configurazione dal file .env.
    """
    load_dotenv()
    return {
        "DB_PATH": os.getenv("DB_PATH", "nft_data.sqlite3"),
        "API_ENDPOINT": os.getenv("API_ENDPOINT"),
        "QAPIKEY": os.getenv("QAPIKEY"),
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
        "TELEGRAM_MONITORING_CHAT_ID": os.getenv("TELEGRAM_MONITORING_CHAT_ID"),
        "TELEGRAM_CHANNEL_CHAT_ID": os.getenv("TELEGRAM_CHANNEL_CHAT_ID"),
        "CSV_HISTORICAL_DATA_PATH": os.getenv("CSV_HISTORICAL_DATA_PATH"),
        "MOCK_API_MODE": os.getenv("MOCK_API_MODE"),
        "MOCK_API_LOCAL_FILE": os.getenv("MOCK_API_LOCAL_FILE"),
        "SHORT_MA_DAYS": os.getenv("SHORT_MA_DAYS"),
        "LONG_MA_DAYS": os.getenv("LONG_MA_DAYS"),
        "ALLOWED_TELEGRAM_IDS": os.getenv("ALLOWED_TELEGRAM_IDS"),
    }