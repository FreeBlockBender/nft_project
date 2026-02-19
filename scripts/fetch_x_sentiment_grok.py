#!/usr/bin/env python3
"""
Fetch X (Twitter) sentiment for top 100 NFT collections using Grok API.
Runs monthly per collection (~3 collections per day).
Uses natural language analysis to gauge community sentiment, engagement, and market perception.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from app.config.config import load_config
from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
from app.telegram.utils.telegram_notifier import send_telegram_message
import httpx
import json

def get_grok_x_sentiment_prompt(collection_name: str, x_handle: str) -> str:
    """
    Generate a sophisticated prompt for Grok to analyze X sentiment.
    
    Args:
        collection_name: NFT collection name
        x_handle: X (Twitter) handle without @
        
    Returns:
        Formatted prompt for Grok API
    """
    
    if not x_handle or x_handle.strip() == "":
        return ""
    
    prompt = f"""
Analyze the X (Twitter) sentiment and social engagement for the NFT collection "{collection_name}" (X handle: @{x_handle}).

Please provide a structured analysis containing:

1. SENTIMENT SCORE (1-100): Overall sentiment toward this collection on X, where:
   - 80-100: Extremely bullish (strong hype, positive announcements, organic growth)
   - 60-79: Bullish (positive sentiment, growing interest)
   - 40-59: Neutral/Mixed (balanced discussion, some concerns)
   - 20-39: Bearish (negative sentiment, concerns dominate)
   - 1-19: Extremely bearish (severe criticism, distrust, low engagement)

2. SENTIMENT CATEGORY: One of [EXTREMELY_BULLISH, BULLISH, NEUTRAL, BEARISH, EXTREMELY_BEARISH]

3. BULLISH INDICATORS (comma-separated): What's driving positive sentiment?
   Examples: new partnerships, releases, floor price appreciation, community growth, NFT trending, developer updates, big wallet purchases

4. BEARISH INDICATORS (comma-separated): What's driving negative sentiment or concerns?
   Examples: price decline, low volume, founder controversies, missed roadmap goals, community frustration, low floor bids

5. KEY TOPICS (comma-separated): Top 3-5 discussions happening around this collection
   Examples: upcoming feature, community speculation, competitive comparison, utility announcement

6. COMMUNITY ENGAGEMENT (1-10): Level of active, organic discussion (not spam/bots)
   - 8-10: Very high organic engagement, vibrant community
   - 5-7: Moderate engagement, steady discussions
   - 1-4: Low engagement, mostly silent collection

7. VOLUME_ACTIVITY (1-10): Trading volume and market activity sentiment
   - 8-10: High volume, active trading, strong demand signals
   - 5-7: Moderate volume, steady trading
   - 1-4: Low volume, minimal trading activity

8. SUMMARY (1-2 sentences): Brief overall assessment of the collection's current perception on X

Format your response as JSON with these exact keys:
{{
    "sentiment_score": <number 1-100>,
    "sentiment_category": "<category>",
    "bullish_indicators": "<comma-separated list>",
    "bearish_indicators": "<comma-separated list>",
    "key_topics": "<comma-separated list>",
    "community_engagement": <number 1-10>,
    "volume_activity": <number 1-10>,
    "summary": "<brief assessment>"
}}
"""
    return prompt.strip()


def fetch_collections_needing_update(top_n: int = 100) -> list:
    """
    Fetch top N collections that need X sentiment update (not updated in last 30 days).
    
    Args:
        top_n: Top N rankings to consider (default 100)
        
    Returns:
        List of tuples (collection_identifier, slug, chain, x_page, ranking)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get top 100 collections from latest data
    cursor.execute("""
    SELECT DISTINCT 
        h.collection_identifier,
        h.slug,
        h.chain,
        nc.x_page,
        h.ranking
    FROM historical_nft_data h
    LEFT JOIN nft_collections nc ON h.slug = nc.slug AND h.chain = nc.chain
    WHERE h.ranking < ? AND h.ranking IS NOT NULL
    AND nc.x_page IS NOT NULL AND nc.x_page != ''
    ORDER BY h.ranking ASC
    LIMIT ?
    """, (top_n, top_n))
    
    top_collections = cursor.fetchall()
    conn.close()
    
    if not top_collections:
        return []
    
    # Filter by monthly update schedule
    collections_to_update = []
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.utcnow()
    thirty_days_ago = (now - timedelta(days=30)).isoformat()
    
    for collection_id, slug, chain, x_page, ranking in top_collections:
        # Check if we have recent sentiment data
        cursor.execute("""
        SELECT date FROM nft_x_sentiment 
        WHERE collection_identifier = ? AND chain = ?
        ORDER BY date DESC LIMIT 1
        """, (collection_id, chain))
        
        result = cursor.fetchone()
        last_update_date = result[0] if result else None
        
        # Add to update list if no data or older than 30 days
        if not last_update_date or last_update_date < thirty_days_ago:
            collections_to_update.append((collection_id, slug, chain, x_page, ranking))
    
    conn.close()
    return collections_to_update


async def call_grok_api(prompt: str, config: dict) -> dict:
    """
    Call Grok API with the sentiment analysis prompt.
    
    Args:
        prompt: Analysis prompt for Grok
        config: Configuration dict with GROK_API_KEY and GROK_API_ENDPOINT
        
    Returns:
        Parsed JSON response from Grok
    """
    
    logger = logging.getLogger(__name__)
    
    api_key = config.get("GROK_API_KEY")
    api_endpoint = config.get("GROK_API_ENDPOINT") or "https://api.x.ai/v1/chat/completions"
    
    if not api_key:
        logger.error("GROK_API_KEY not configured")
        return {}
    
    # Support both Bearer token and direct key formats
    auth_header = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
    
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "grok-3",  # Try grok-3 (most recent stable model)
        "messages": [
            {
                "role": "system",
                "content": "You are an expert NFT market analyst specializing in social sentiment analysis. Respond with valid JSON only, no markdown formatting."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(api_endpoint, json=payload, headers=headers)
            
            # Log detailed request/response for debugging
            logger.debug(f"Grok Request - Endpoint: {api_endpoint}")
            logger.debug(f"Grok Request - Headers: {headers}")
            logger.debug(f"Grok Response Status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Grok API returned {response.status_code}: {response.text}")
                return {}
            
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                # Parse JSON from response
                try:
                    parsed = json.loads(content)
                    return parsed
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse Grok response as JSON: {e}")
                    logger.error(f"Raw response: {content}")
                    return {}
            else:
                logger.error(f"Unexpected Grok API response: {result}")
                return {}
                
    except httpx.HTTPError as e:
        logger.error(f"Grok API error: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error calling Grok API: {e}")
        return {}


def store_sentiment_result(collection_id: str, slug: str, chain: str, sentiment_data: dict) -> bool:
    """
    Store Grok sentiment result in database.
    
    Args:
        collection_id: Collection identifier
        slug: Collection slug
        chain: Blockchain chain
        sentiment_data: Parsed sentiment data from Grok
        
    Returns:
        True if successful, False otherwise
    """
    
    logger = logging.getLogger(__name__)
    
    if not sentiment_data:
        logger.warning(f"No sentiment data to store for {slug} on {chain}")
        return False
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        now = datetime.utcnow()
        current_date = now.date().isoformat()
        current_timestamp = now.isoformat()
        
        cursor.execute("""
        INSERT OR REPLACE INTO nft_x_sentiment (
            collection_identifier, slug, chain, date, timestamp,
            sentiment_score, sentiment_category,
            bullish_indicators, bearish_indicators,
            key_topics, community_engagement, volume_activity,
            raw_grok_response, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            collection_id, slug, chain, current_date, current_timestamp,
            sentiment_data.get("sentiment_score", 0),
            sentiment_data.get("sentiment_category", "NEUTRAL"),
            sentiment_data.get("bullish_indicators", ""),
            sentiment_data.get("bearish_indicators", ""),
            sentiment_data.get("key_topics", ""),
            sentiment_data.get("community_engagement", 5),
            sentiment_data.get("volume_activity", 5),
            json.dumps(sentiment_data),
            current_timestamp
        ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Stored sentiment for {slug} ({chain}): score={sentiment_data.get('sentiment_score')}, category={sentiment_data.get('sentiment_category')}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to store sentiment for {slug} ({chain}): {e}")
        return False


async def process_collections(max_per_run: int = 3):
    """
    Process X sentiment for collections needing updates.
    
    Args:
        max_per_run: Maximum collections to process in one run (default 3 per day)
    """
    
    setup_logging()
    logger = logging.getLogger(__name__)
    config = load_config()
    
    logger.info(f"Starting X sentiment analysis (max {max_per_run} collections)...")
    
    try:
        # Fetch collections needing updates
        collections = fetch_collections_needing_update(top_n=100)
        
        if not collections:
            logger.info("No collections need sentiment update.")
            await send_telegram_message(
                "🔍 X Sentiment Analysis: No collections need updates (all within 30-day window).",
                config.get("TELEGRAM_MONITORING_CHAT_ID")
            )
            return
        
        logger.info(f"Found {len(collections)} collections needing updates, processing top {max_per_run}...")
        
        processed_count = 0
        success_count = 0
        
        for collection_id, slug, chain, x_handle, ranking in collections[:max_per_run]:
            # Get collection name (open fresh connection for this query)
            conn_lookup = get_db_connection()
            cursor_lookup = conn_lookup.cursor()
            cursor_lookup.execute(
                "SELECT name FROM nft_collections WHERE slug = ? AND chain = ?",
                (slug, chain)
            )
            name_result = cursor_lookup.fetchone()
            collection_name = name_result[0] if name_result else slug
            conn_lookup.close()  # Close immediately after lookup
            
            # Clean x_handle (remove @ if present)
            clean_handle = x_handle.lstrip('@') if x_handle else None
            
            logger.info(f"Processing {collection_name} (@{clean_handle}) - Ranking: {ranking}")
            
            # Generate prompt and call Grok
            prompt = get_grok_x_sentiment_prompt(collection_name, clean_handle)
            
            if not prompt or not clean_handle:
                logger.warning(f"Skipping {slug}: no valid X handle")
                continue
            
            sentiment_data = await call_grok_api(prompt, config)
            
            if sentiment_data and store_sentiment_result(collection_id, slug, chain, sentiment_data):
                success_count += 1
            
            processed_count += 1
            
            # Rate limiting - small delay between API calls
            if processed_count < max_per_run:
                await asyncio.sleep(2)
        
        # Send summary to monitoring chat
        summary_msg = f"✅ X Sentiment Analysis Complete\n\n📊 Processed: {processed_count} collections\n✔️ Successful: {success_count}\n\nNext: Run again in 24 hours to process next batch."
        await send_telegram_message(
            summary_msg,
            config.get("TELEGRAM_MONITORING_CHAT_ID")
        )
        
        logger.info(f"X sentiment analysis complete: {success_count}/{processed_count} successful")
        
    except Exception as e:
        logger.error(f"X sentiment analysis failed: {e}")
        await send_telegram_message(
            f"❌ X Sentiment Analysis Error: {str(e)}",
            config.get("TELEGRAM_MONITORING_CHAT_ID")
        )


def main():
    """Entry point."""
    asyncio.run(process_collections(max_per_run=3))


if __name__ == "__main__":
    main()
