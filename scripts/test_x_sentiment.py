#!/usr/bin/env python3
"""
Test script for X sentiment commands
Usage: python scripts/test_x_sentiment.py <slug> <chain>
       python scripts/test_x_sentiment.py --recent
"""

import sys
import logging
from app.database.db_connection import get_db_connection
from app.config.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def test_x_sentiment(slug, chain):
    """Test /x_sentiment command."""
    print(f"\n🔍 Fetching X sentiment for {slug} on {chain}...")
    
    try:
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
            print(f"❌ No X sentiment data found for {slug} on {chain}.")
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
{emoji} X Sentiment for {slug.upper()} ({chain})

📊 Analysis Date: {date}

Overall Score: {score}/100 ({category})

Community Engagement: {engagement}/10 {"🔥" if engagement >= 7 else "❄️" if engagement <= 3 else ""}
Trading Activity: {volume}/10 {"⚡" if volume >= 7 else "💤" if volume <= 3 else ""}

Bullish Signals:
{bullish if bullish else "None identified"}

Bearish Signals:
{bearish if bearish else "None identified"}

Key Topics:
{topics if topics else "None identified"}

Summary:
{summary}

---
Analysis powered by Grok API (monthly updates for top 100 collections)
"""
        print(message)
        
    except Exception as e:
        logger.error(f"Error fetching X sentiment: {e}", exc_info=True)
        print(f"❌ Error: {str(e)}")


def test_x_sentiment_top():
    """Test /x_sentiment_top command."""
    print(f"\n📊 Fetching top bullish and bearish collections by X sentiment...")
    
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
        
        if not bullish and not bearish:
            print("❌ No X sentiment data available in database.")
            return
        
        message = "📊 X Sentiment Rankings (Latest)\n\n"
        
        message += "🚀 Most Bullish Collections:\n"
        for slug, chain, score, category, date in bullish:
            message += f"  • {slug} ({chain}): {score}/100\n"
        
        message += "\n📉 Most Bearish Collections:\n"
        for slug, chain, score, category, date in bearish:
            message += f"  • {slug} ({chain}): {score}/100\n"
        
        if bullish:
            message += f"\nLast updated: {bullish[0][4]}"
        
        print(message)
        
    except Exception as e:
        logger.error(f"Error fetching top sentiments: {e}", exc_info=True)
        print(f"❌ Error: {str(e)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/test_x_sentiment.py <slug> <chain>   # Test specific collection")
        print("  python scripts/test_x_sentiment.py --recent         # Test top collections")
        print("\nExample:")
        print("  python scripts/test_x_sentiment.py claynosaurz solana")
        print("  python scripts/test_x_sentiment.py --recent")
        sys.exit(1)
    
    if sys.argv[1] == "--recent":
        test_x_sentiment_top()
    else:
        if len(sys.argv) < 3:
            print("❌ Please provide both slug and chain")
            print("Example: python scripts/test_x_sentiment.py claynosaurz solana")
            sys.exit(1)
        
        slug = sys.argv[1].lower()
        chain = sys.argv[2].lower()
        test_x_sentiment(slug, chain)
