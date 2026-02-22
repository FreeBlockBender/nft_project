"""
Module: import_social_hype.py
Importa il sentiment e l'hype del mercato NFT usando l'API di Grok.
Misura le "vibes" generali del mercato NFT attraverso analisi AI del sentiment.
"""

import requests
import json
import logging
from datetime import datetime
from app.config.config import load_config
from app.database.db_connection import get_db_connection
from app.telegram.utils.telegram_notifier import send_telegram_message, get_monitoring_chat_id
import asyncio

logger = logging.getLogger(__name__)


def get_nft_market_sentiment():
    """
    Chiama l'API di Grok per analizzare il sentiment attuale del mercato NFT.
    Restituisce score di hype, sentiment e trend.
    """
    config = load_config()
    grok_api_key = config.get("GROK_API_KEY")
    grok_endpoint = config.get("GROK_API_ENDPOINT", "https://api.x.ai/v1")

    if not grok_api_key:
        logger.error("GROK_API_KEY non configurato nel file .env")
        return None

    # Prompt per Grok: analizzare il sentiment del mercato NFT
    prompt = """
    Analyze the current global NFT market sentiment based on real-time data from:
    1. Recent NFT market trends (e.g., trading volume, floor prices, sales data).
    2. Crypto community sentiment (e.g., discussions on forums, social media).
    3. Activity on major NFT platforms (OpenSea, Magic Eden, Blur, etc.).
    4. Recent news on blockchain and NFTs (e.g., regulatory updates, tech advancements).
    5. Attitudes of creators, investors, and influencers (e.g., statements, investments).

    Use available tools like web search, X searches, and browsing to gather fresh, diverse sources. Ensure analysis is balanced and evidence-based.

    Provide the response STRICTLY in this valid JSON format without any additional text or markdown:

    {
        "hype_score": <integer from 0 to 100>,
        "sentiment": "<POSITIVE|NEUTRAL|NEGATIVE>",
        "trend": "<UP|STABLE|DOWN>",
        "keywords": "<3-5 keywords separated by comma>",
        "summary": "<summary in English, maximum 200 characters>",
        "reasoning": "<brief explanation of the score, including key evidence>"
    }

    Be STRICT in the JSON format - no text before, after, or outside the object.
    """

    try:
        headers = {
            "Authorization": f"Bearer {grok_api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "grok-3",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }

        # Normalize endpoint - remove trailing /chat/completions if already present
        clean_endpoint = grok_endpoint.rstrip('/')
        if clean_endpoint.endswith("/chat/completions"):
            clean_endpoint = clean_endpoint[:-len("/chat/completions")]

        response = requests.post(
            f"{clean_endpoint}/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            logger.debug(f"Grok response: {content}")

            # Estrai il JSON dalla risposta
            try:
                # Prova a trovare il JSON nella risposta
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    sentiment_data = json.loads(json_str)
                    return sentiment_data
                else:
                    logger.error(f"Impossibile trovare JSON nella risposta: {content}")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"Errore parsing JSON da Grok: {e}")
                logger.error(f"Contenuto: {content}")
                return None
        else:
            logger.error(f"Risposta Grok non valida: {result}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Errore API Grok: {e}")
        if hasattr(e.response, 'text'):
            logger.error(f"Response body: {e.response.text}")
        return None


def save_social_hype_to_db(sentiment_data):
    """
    Salva i dati di sentiment nel database.
    """
    if not sentiment_data:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        now = datetime.now()
        today_date = now.strftime("%Y-%m-%d")
        timestamp = now.isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO nft_social_hype 
            (date, timestamp, hype_score, sentiment, trend, keywords, summary, raw_response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today_date,
            timestamp,
            sentiment_data.get("hype_score", 0),
            sentiment_data.get("sentiment", "NEUTRAL"),
            sentiment_data.get("trend", "STABLE"),
            sentiment_data.get("keywords", ""),
            sentiment_data.get("summary", ""),
            json.dumps(sentiment_data),
            timestamp
        ))

        conn.commit()
        logger.info(f"Social hype salvato nel database: score={sentiment_data.get('hype_score')}")
        return True

    except Exception as e:
        logger.error(f"Errore saving social hype: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def import_nft_social_hype():
    """
    Funzione principale: importa il sentiment del mercato NFT via Grok e lo salva nel DB.
    """
    logger.info("Inizio import social hype NFT...")
    
    monitoring_chat_id = get_monitoring_chat_id()

    sentiment_data = get_nft_market_sentiment()

    if sentiment_data:
        if save_social_hype_to_db(sentiment_data):
            message = (
                f"🎨 <b>NFT Social Hype Update</b>\n\n"
                f"📊 Hype Score: {sentiment_data.get('hype_score')}/100\n"
                f"😊 Sentiment: {sentiment_data.get('sentiment')}\n"
                f"📈 Trend: {sentiment_data.get('trend')}\n"
                f"🏷️ Keywords: {sentiment_data.get('keywords')}\n"
                f"📝 Summary: {sentiment_data.get('summary')}\n\n"
                f"✅ Social hype aggiornato con successo!"
            )
            logger.info("Social hype importato correttamente!")
            asyncio.run(send_telegram_message(message, monitoring_chat_id))
        else:
            logger.error("Errore nel salvataggio dei dati di hype nel database")
            asyncio.run(send_telegram_message(
                "❌ Errore nel salvataggio dei dati di social hype nel database",
                monitoring_chat_id
            ))
    else:
        logger.error("Errore nel recupero dei dati di sentiment da Grok")
        asyncio.run(send_telegram_message(
            "❌ Errore nel recupero dei dati di sentiment da Grok",
            monitoring_chat_id
        ))


if __name__ == "__main__":
    from app.config.logging_config import setup_logging
    setup_logging()
    import_nft_social_hype()
