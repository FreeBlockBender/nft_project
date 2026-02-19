#!/usr/bin/env python3
"""
Query and analyze X sentiment trends for collections.
Useful for identifying sentiment shifts and community engagement patterns.
"""

from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
import logging
from datetime import datetime, timedelta

def view_latest_sentiment_snapshot():
    """Display latest X sentiment for all collections analyzed."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get latest analysis date
    cursor.execute("SELECT MAX(date) FROM nft_x_sentiment")
    latest_date_result = cursor.fetchone()
    
    if not latest_date_result or not latest_date_result[0]:
        print("❌ No X sentiment data found in database.")
        conn.close()
        return
    
    latest_date = latest_date_result[0]
    print(f"\n📊 X SENTIMENT SNAPSHOT - {latest_date}")
    print("=" * 80)
    
    # Get all sentiment data from latest date with rankings
    cursor.execute("""
    SELECT 
        xs.slug,
        xs.chain,
        xs.sentiment_score,
        xs.sentiment_category,
        xs.community_engagement,
        xs.volume_activity,
        xs.summary,
        hnd.ranking
    FROM nft_x_sentiment xs
    LEFT JOIN historical_nft_data hnd ON xs.slug = hnd.slug AND xs.chain = hnd.chain
    WHERE xs.date = ?
    ORDER BY hnd.ranking ASC, xs.sentiment_score DESC
    """, (latest_date,))
    
    results = cursor.fetchall()
    
    if not results:
        print(f"No sentiment data found for {latest_date}")
        conn.close()
        return
    
    # Format and display results
    print(f"\n{'Rank':<6} {'Collection':<40} {'Chain':<12} {'Score':<8} {'Category':<18} {'Engagement':<11} {'Volume'}")
    print("-" * 120)
    
    for slug, chain, score, category, engagement, volume, summary, ranking in results:
        emoji = {
            'EXTREMELY_BULLISH': '🚀🚀',
            'BULLISH': '📈',
            'NEUTRAL': '➡️',
            'BEARISH': '📉',
            'EXTREMELY_BEARISH': '🔴🔴'
        }.get(category, '❓')
        
        rank_str = f"#{ranking}" if ranking else "N/A"
        print(f"{rank_str:<6} {slug:<40} {chain:<12} {score:<8} {emoji} {category:<15} {engagement}/10{' ':<5} {volume}/10")
    
    # Summary statistics
    print("\n📈 SUMMARY STATISTICS")
    print("-" * 80)
    
    cursor.execute("""
    SELECT 
        COUNT(DISTINCT collection_identifier) as total_collections,
        AVG(sentiment_score) as avg_score,
        MIN(sentiment_score) as min_score,
        MAX(sentiment_score) as max_score,
        AVG(community_engagement) as avg_engagement,
        AVG(volume_activity) as avg_volume
    FROM nft_x_sentiment
    WHERE date = ?
    """, (latest_date,))
    
    stats = cursor.fetchone()
    total, avg_score, min_score, max_score, avg_eng, avg_vol = stats
    
    print(f"Collections Analyzed: {total}")
    print(f"Average Score: {avg_score:.1f}/100")
    print(f"Score Range: {min_score} - {max_score}")
    print(f"Avg Community Engagement: {avg_eng:.1f}/10")
    print(f"Avg Trading Activity: {avg_vol:.1f}/10")
    
    # Sentiment distribution
    print("\n🎯 SENTIMENT DISTRIBUTION")
    print("-" * 80)
    
    cursor.execute("""
    SELECT 
        sentiment_category,
        COUNT(*) as count
    FROM nft_x_sentiment
    WHERE date = ?
    GROUP BY sentiment_category
    ORDER BY count DESC
    """, (latest_date,))
    
    dist = cursor.fetchall()
    for category, count in dist:
        emoji = {
            'EXTREMELY_BULLISH': '🚀🚀',
            'BULLISH': '📈',
            'NEUTRAL': '➡️',
            'BEARISH': '📉',
            'EXTREMELY_BEARISH': '🔴🔴'
        }.get(category, '❓')
        percent = (count / total) * 100 if total > 0 else 0
        print(f"{emoji} {category:<20} {count:>3} ({percent:>5.1f}%)")
    
    # Most bullish and bearish
    print("\n🚀 TOP 5 MOST BULLISH")
    print("-" * 80)
    
    cursor.execute("""
    SELECT slug, chain, sentiment_score, community_engagement
    FROM nft_x_sentiment
    WHERE date = ?
    ORDER BY sentiment_score DESC
    LIMIT 5
    """, (latest_date,))
    
    for slug, chain, score, engagement in cursor.fetchall():
        print(f"  ✅ {slug:<30} ({chain:<10}) - Score: {score}/100, Engagement: {engagement}/10")
    
    print("\n📉 TOP 5 MOST BEARISH")
    print("-" * 80)
    
    cursor.execute("""
    SELECT slug, chain, sentiment_score, community_engagement
    FROM nft_x_sentiment
    WHERE date = ?
    ORDER BY sentiment_score ASC
    LIMIT 5
    """, (latest_date,))
    
    for slug, chain, score, engagement in cursor.fetchall():
        print(f"  ❌ {slug:<30} ({chain:<10}) - Score: {score}/100, Engagement: {engagement}/10")
    
    conn.close()
    print("\n")


def view_sentiment_history(slug: str, chain: str, days: int = 90):
    """Display sentiment history for specific collection."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n📈 X SENTIMENT HISTORY - {slug.upper()} ({chain})")
    print("=" * 80)
    
    # Get history
    cursor.execute("""
    SELECT 
        date,
        sentiment_score,
        sentiment_category,
        community_engagement,
        volume_activity,
        bullish_indicators,
        bearish_indicators
    FROM nft_x_sentiment
    WHERE slug = ? AND chain = ?
    ORDER BY date DESC
    LIMIT ?
    """, (slug, chain, days // 30 + 1))  # Monthly updates, so fetch all available
    
    results = cursor.fetchall()
    
    if not results:
        print(f"❌ No sentiment history found for {slug} on {chain}")
        conn.close()
        return
    
    print(f"\n{'Date':<12} {'Score':<8} {'Category':<18} {'Engagement':<12} {'Volume':<8}")
    print("-" * 80)
    
    for date, score, category, engagement, volume, bullish, bearish in results:
        emoji = {
            'EXTREMELY_BULLISH': '🚀🚀',
            'BULLISH': '📈',
            'NEUTRAL': '➡️',
            'BEARISH': '📉',
            'EXTREMELY_BEARISH': '🔴🔴'
        }.get(category, '❓')
        
        print(f"{date:<12} {score:<8} {emoji} {category:<15} {engagement}/10{' ':<5} {volume}/10")
    
    # Show trend if multiple data points
    if len(results) > 1:
        oldest_score = results[-1][1]
        newest_score = results[0][1]
        change = newest_score - oldest_score
        trend = "📈 UP" if change > 0 else "📉 DOWN" if change < 0 else "➡️ STABLE"
        print(f"\nTrend: {trend} ({change:+d} points)")
    
    conn.close()
    print("\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 2:
        # View history for specific collection
        slug = sys.argv[1]
        chain = sys.argv[2]
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 90
        view_sentiment_history(slug, chain, days)
    else:
        # View latest snapshot
        view_latest_sentiment_snapshot()
