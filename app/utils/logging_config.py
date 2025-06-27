import logging

def setup_logging():
    """
    Configura il logging globale con timestamp formato richiesto (YYYY-MM-DD HH:MM:SS.sss).
    Da importare e richiamare una sola volta (tipicamente in main.py).
    """
    # Verifica se il root logger ha già handler per evitare setup duplicati
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )