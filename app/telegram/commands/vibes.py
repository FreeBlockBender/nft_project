"""
Telegram Command: /vibes
Mostra il social hype e sentiment attuale del mercato NFT.
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.database.db_connection import get_db_connection
import logging

logger = logging.getLogger(__name__)


async def vibes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mostra il social hype attuale del mercato NFT.
    Recupera i dati di sentiment più recenti dal database.
    """
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await access_denied(update)
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Recupera il record più recente
        cursor.execute("""
            SELECT date, hype_score, sentiment, trend, keywords, summary, created_at
            FROM nft_social_hype
            ORDER BY date DESC
            LIMIT 1
        """)

        result = cursor.fetchone()
        conn.close()

        if result:
            date, hype_score, sentiment, trend, keywords, summary, created_at = result

            # Emoji basati su sentiment e trend
            sentiment_emoji = {
                "POSITIVE": "🟢",
                "NEUTRAL": "🟡",
                "NEGATIVE": "🔴"
            }
            trend_emoji = {
                "UP": "📈",
                "STABLE": "➡️",
                "DOWN": "📉"
            }

            # Emoji per hype score
            if hype_score >= 75:
                hype_emoji = "🚀"
            elif hype_score >= 50:
                hype_emoji = "📊"
            else:
                hype_emoji = "❄️"

            message = (
                f"🎨 **NFT Market Vibes** ({date})\n\n"
                f"{hype_emoji} **Hype Score:** {hype_score}/100\n"
                f"{sentiment_emoji.get(sentiment, '❓')} **Sentiment:** {sentiment}\n"
                f"{trend_emoji.get(trend, '❓')} **Trend:** {trend}\n\n"
                f"🏷️ **Keywords:** {keywords}\n\n"
                f"📝 **Summary:**\n{summary}\n\n"
                f"🕐 Updated: {created_at}"
            )

            await update.message.reply_text(message, parse_mode="Markdown")

        else:
            await update.message.reply_text(
                "❌ Nessun dato di social hype disponibile.\n"
                "Esegui `/import_vibes` per generare i dati."
            )

    except Exception as e:
        logger.error(f"Errore nel comando vibes: {e}")
        await update.message.reply_text(f"❌ Errore: {str(e)}")


async def import_vibes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Genera i dati di social hype usando l'API di Grok.
    Questo comando avvia l'import di sentiment in tempo reale.
    """
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await access_denied(update)
        return

    try:
        await update.message.reply_text("🔄 Sto analizzando le vibes del mercato NFT con Grok...")

        from app.data_import.import_social_hype import get_nft_market_sentiment, save_social_hype_to_db

        sentiment_data = get_nft_market_sentiment()

        if sentiment_data and save_social_hype_to_db(sentiment_data):
            hype_score = sentiment_data.get("hype_score", 0)
            sentiment = sentiment_data.get("sentiment", "NEUTRAL")
            trend = sentiment_data.get("trend", "STABLE")
            keywords = sentiment_data.get("keywords", "")
            summary = sentiment_data.get("summary", "")

            message = (
                f"✅ **Vibes Aggiornate!**\n\n"
                f"📊 Hype Score: {hype_score}/100\n"
                f"😊 Sentiment: {sentiment}\n"
                f"📈 Trend: {trend}\n\n"
                f"🏷️ Keywords: {keywords}\n"
                f"📝 {summary}"
            )
            await update.message.reply_text(message, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "❌ Errore nell'analisi delle vibes. Verifica la configurazione di Grok."
            )

    except Exception as e:
        logger.error(f"Errore nel comando import_vibes: {e}")
        await update.message.reply_text(f"❌ Errore: {str(e)}")


# Handler exports
vibes_handler = CommandHandler("vibes", vibes)
import_vibes_handler = CommandHandler("import_vibes", import_vibes)
