#!/usr/bin/env python3
"""
Telegram command to view X sentiment for specific collection.
Format: /x_sentiment @handle or /x_sentiment slug-name chain
"""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from app.telegram.utils.auth import is_authorized, access_denied
from app.database.db_connection import get_db_connection
import logging

logger = logging.getLogger(__name__)


async def x_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent X sentiment analysis for a collection."""
    
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/x_sentiment <slug> <chain>\n\n"
            "Example: /x_sentiment claynosaurz solana\n\n"
            "Shows latest X sentiment analysis for a collection."
        )
        return
    
    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Please provide both slug and chain.\n"
                "Example: /x_sentiment claynosaurz solana"
            )
            return
        
        slug = context.args[0].lower()
        chain = context.args[1].lower()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get latest sentiment data
        cursor.execute("""
        SELECT 
            sentiment_score,
            sentiment_category,
            bullish_indicators,
            bearish_indicators,
            key_topics,
            community_engagement,
            volume_activity,
            summary,
            date
        FROM nft_x_sentiment
        WHERE slug = ? AND chain = ?
        ORDER BY date DESC
        LIMIT 1
        """, (slug, chain))
        
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await update.message.reply_text(
                f"❌ No X sentiment data found for {slug} on {chain}.\n"
                "Sentiment analysis may not be available yet for this collection."
            )
            return
        
        (score, category, bullish, bearish, topics, engagement, volume, summary, date) = result
        
        # Format sentiment emoji
        emoji = {
            'EXTREMELY_BULLISH': '🚀🚀',
            'BULLISH': '📈',
            'NEUTRAL': '➡️',
            'BEARISH': '📉',
            'EXTREMELY_BEARISH': '🔴🔴'
        }.get(category, '❓')
        
        message = f"""
{emoji} **X Sentiment for {slug.upper()} ({chain})**

📊 **Analysis Date:** {date}

**Overall Score:** {score}/100 ({category})

**Community Engagement:** {engagement}/10 {"🔥" if engagement >= 7 else "❄️" if engagement <= 3 else ""}
**Trading Activity:** {volume}/10 {"⚡" if volume >= 7 else "💤" if volume <= 3 else ""}

**Bullish Signals:**
{bullish if bullish else "None identified"}

**Bearish Signals:**
{bearish if bearish else "None identified"}

**Key Topics:**
{topics if topics else "None identified"}

**Summary:**
{summary}

---
*Analysis powered by Grok API (monthly updates for top 100 collections)*
"""
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error fetching X sentiment: {e}")
        await update.message.reply_text(
            f"❌ Failed to retrieve sentiment data: {str(e)}"
        )


async def x_sentiment_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show top bullish and bearish collections by X sentiment."""
    
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get most bullish collections
        cursor.execute("""
        SELECT 
            slug,
            chain,
            sentiment_score,
            sentiment_category,
            date
        FROM nft_x_sentiment
        WHERE date = (SELECT MAX(date) FROM nft_x_sentiment)
        ORDER BY sentiment_score DESC
        LIMIT 5
        """)
        
        bullish = cursor.fetchall()
        
        # Get most bearish collections
        cursor.execute("""
        SELECT 
            slug,
            chain,
            sentiment_score,
            sentiment_category,
            date
        FROM nft_x_sentiment
        WHERE date = (SELECT MAX(date) FROM nft_x_sentiment)
        ORDER BY sentiment_score ASC
        LIMIT 5
        """)
        
        bearish = cursor.fetchall()
        conn.close()
        
        message = "📊 **X Sentiment Rankings (Latest)**\n\n"
        
        message += "🚀 **Most Bullish Collections:**\n"
        for slug, chain, score, category, date in bullish:
            message += f"  • {slug} ({chain}): {score}/100\n"
        
        message += "\n📉 **Most Bearish Collections:**\n"
        for slug, chain, score, category, date in bearish:
            message += f"  • {slug} ({chain}): {score}/100\n"
        
        message += f"\n*Last updated: {date}*"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error fetching top sentiments: {e}")
        await update.message.reply_text(
            f"❌ Failed to retrieve sentiment rankings: {str(e)}"
        )


# Handler exports for registration in telegram_bot.py
x_sentiment_handler = CommandHandler("x_sentiment", x_sentiment)
x_sentiment_top_handler = CommandHandler("x_sentiment_top", x_sentiment_top)
