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
        "TELEGRAM_GC_DRAFT_CHAT_ID": os.getenv("TELEGRAM_GC_DRAFT_CHAT_ID"),
        "CSV_HISTORICAL_DATA_PATH": os.getenv("CSV_HISTORICAL_DATA_PATH"),
        "MOCK_API_MODE": os.getenv("MOCK_API_MODE"),
        "MOCK_API_LOCAL_FILE": os.getenv("MOCK_API_LOCAL_FILE"),
        "SMA_20": os.getenv("SMA_20"),
        "SMA_50": os.getenv("SMA_50"),
        "SMA_100": os.getenv("SMA_100"),
        "SMA_200": os.getenv("SMA_200"),
        "SMA_20_MISSING_THRESH": os.getenv("SMA_20_MISSING_THRESH"),
        "SMA_50_MISSING_THRESH": os.getenv("SMA_50_MISSING_THRESH"),
        "SMA_100_MISSING_THRESH": os.getenv("SMA_100_MISSING_THRESH"),
        "SMA_200_MISSING_THRESH": os.getenv("SMA_200_MISSING_THRESH"),
        "ALLOWED_TELEGRAM_IDS": os.getenv("ALLOWED_TELEGRAM_IDS"),
    }