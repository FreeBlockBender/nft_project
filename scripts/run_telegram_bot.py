# Script di lancio per avviare il bot Telegram

from app.telegram.telegram_bot import main

def run_bot():
    """
    Entry point per l’esecuzione del bot Telegram.
    Richiama la funzione main() dal modulo app.telegram_bot.
    """
    main()

if __name__ == "__main__":
    run_bot()