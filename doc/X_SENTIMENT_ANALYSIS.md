# X Sentiment Analysis System - Implementation Guide

## Overview

This system analyzes X (Twitter) sentiment for the top 100 NFT collections on a monthly basis, using the **Grok API** to gauge community sentiment, track engagement, and identify market trends. Processing is rate-limited to ~3 collections per day to manage API costs.

---

## Architecture

### Data Flow

```
Top 100 Collections (ranking < 100)
    ↓
Grok API Analysis (monthly per collection)
    ↓
Sentiment Score + Community Metrics
    ↓
SQLite Storage (nft_x_sentiment table)
    ↓
Telegram Commands + Analytics
```

### Database Schema

#### `nft_x_sentiment` Table
Stores monthly X sentiment analysis results for each collection.

```sql
CREATE TABLE nft_x_sentiment (
    id INTEGER PRIMARY KEY,
    collection_identifier TEXT,
    slug TEXT,
    chain TEXT,
    date TEXT,                           -- Analysis date (YYYY-MM-DD)
    timestamp TEXT,                      -- ISO timestamp
    sentiment_score INTEGER,             -- 1-100 scale
    sentiment_category TEXT,             -- EXTREMELY_BULLISH, BULLISH, NEUTRAL, BEARISH, EXTREMELY_BEARISH
    bullish_indicators TEXT,             -- Comma-separated list
    bearish_indicators TEXT,             -- Comma-separated list
    key_topics TEXT,                     -- Top 3-5 discussions
    community_engagement INTEGER,        -- 1-10 (engagement quality)
    volume_activity INTEGER,             -- 1-10 (trading volume signals)
    raw_grok_response TEXT,              -- Full JSON response
    created_at TEXT,                     -- Insertion timestamp
    UNIQUE(collection_identifier, chain, date)
);
```

**Key Indices:**
- `idx_x_sentiment_collection_date`: For efficient collection + date queries

#### `nft_collections` Table
Updated to include `x_page` column (X handle).

```sql
ALTER TABLE nft_collections ADD COLUMN x_page TEXT DEFAULT NULL;
-- Example: x_page = 'Claynosaurz' (without @, without https://x.com/)
```

#### `nft_x_sentiment_schedule` Table
Tracks update schedule for monthly refreshing.

```sql
CREATE TABLE nft_x_sentiment_schedule (
    collection_identifier TEXT PRIMARY KEY,
    slug TEXT,
    chain TEXT,
    last_updated_date TEXT,
    last_grok_call TEXT,
    status TEXT
);
```

---

## Grok API Prompt Design

The sentiment analysis uses a sophisticated prompt that extracts:

### 1. **Sentiment Score (1-100)**
   - **80-100**: Extremely bullish (strong hype, positive announcements, organic growth)
   - **60-79**: Bullish (positive sentiment, growing interest)
   - **40-59**: Neutral/Mixed (balanced discussion, some concerns)
   - **20-39**: Bearish (negative sentiment, concerns dominate)
   - **1-19**: Extremely bearish (severe criticism, distrust)

### 2. **Sentiment Category**
Classification: `EXTREMELY_BULLISH | BULLISH | NEUTRAL | BEARISH | EXTREMELY_BEARISH`

### 3. **Community Engagement (1-10)**
Quality of organic, non-spam discussion:
- **8-10**: Very high organic engagement, vibrant community
- **5-7**: Moderate engagement, steady discussions
- **1-4**: Low engagement, mostly silent

### 4. **Volume Activity (1-10)**
Trading volume and market activity signals:
- **8-10**: High volume, strong demand signals
- **5-7**: Moderate volume, steady trading
- **1-4**: Low volume, minimal trading

### 5. **Bullish Indicators** (comma-separated)
**Examples:**
- New partnerships
- Features/releases
- Floor price appreciation
- Community growth
- NFT trending
- Developer updates
- Big wallet purchases
- Roadmap milestones

### 6. **Bearish Indicators** (comma-separated)
**Examples:**
- Price decline
- Low volume
- Founder controversies
- Missed roadmap goals
- Community frustration
- Whale selling
- Regulatory concerns
- Exchange delistings

### 7. **Key Topics** (top 3-5 discussions)
**Examples:**
- "Upcoming feature launch"
- "Community speculation on floor"
- "Comparison with competitors"
- "Utility announcement leaked"

### 8. **Summary** (1-2 sentences)
Brief overall assessment of collection perception on X.

---

## Configuration

### Environment Variables

Add these to your `.env`:

```bash
# Grok API Configuration
GROK_API_KEY=xai-xxxxxxxxxxxxxxxxxxxx
GROK_API_ENDPOINT=https://api.x.ai/v1/chat/completions  # Default

# Database
DB_PATH=nft_data.sqlite3

# Telegram (for monitoring)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_MONITORING_CHAT_ID=your_chat_id
```

### Get Grok API Key
1. Go to https://console.x.ai
2. Sign in with X account
3. Create API key
4. Set rate limits to respect budget

---

## Usage

### 1. Setup & Migration

```bash
# Apply migrations to create new tables
python scripts/migrate_add_x_sentiment_table.py

# Verify database
python scripts/verify_database.py
```

### 2. Fetch X Sentiment (3 collections per day)

```bash
# Run daily (processes next 3 collections needing monthly update)
python scripts/fetch_x_sentiment_grok.py
```

**Behavior:**
- Checks top 100 collections
- Finds those not updated in last 30 days
- Processes first 3 (rate-limited)
- Stores results in `nft_x_sentiment` table
- Sends summary to Telegram monitoring chat

### 3. View Sentiment Data

```bash
# Latest snapshot for all collections analyzed
python scripts/view_x_sentiment_data.py

# History for specific collection (last 90 days)
python scripts/view_x_sentiment_data.py claynosaurz solana 90
```

### 4. Telegram Commands

**View sentiment for specific collection:**
```
/x_sentiment claynosaurz solana
```
Shows latest sentiment score, bullish/bearish signals, engagement metrics.

**View sentiment rankings:**
```
/x_sentiment_top
```
Shows top 5 most bullish and bearish collections in latest analysis.

---

## Scheduling

### Recommended Setup (Cron / Task Scheduler)

**Daily at 10:00 AM UTC:**
```bash
0 10 * * * cd /path/to/nft_project && python scripts/fetch_x_sentiment_grok.py
```

**Why 3 per day?**
- Top 100 collections ÷ 30 days = ~3.3 per day
- Spreads monthly updates evenly
- Manageable API cost (~90 calls/month)
- Rate limit friendly (typical 100-1000 calls/day on Grok)

### Expected Timeline
- Day 1-30: All 100 collections get first analysis
- Day 31+: Start refreshing oldest analyses
- Continuous monthly rotation

---

## Grok Response Format

The API expects **valid JSON** response:

```json
{
    "sentiment_score": 72,
    "sentiment_category": "BULLISH",
    "bullish_indicators": "New partnership announced, Floor appreciation, Community growth",
    "bearish_indicators": "Low trading volume, Marketplace saturation",
    "key_topics": "Upcoming roadmap release, Comparison with competitors, New utility rumor",
    "community_engagement": 7,
    "volume_activity": 5,
    "summary": "Strong positive sentiment with active community discussions around upcoming features. Trading volume remains moderate but stable."
}
```

---

## Data Analysis Examples

### Query 1: Most Bullish Collections (Latest)
```sql
SELECT slug, chain, sentiment_score, community_engagement
FROM nft_x_sentiment
WHERE date = (SELECT MAX(date) FROM nft_x_sentiment)
ORDER BY sentiment_score DESC
LIMIT 10;
```

### Query 2: Collections with High Engagement but Low Volume
```sql
SELECT slug, chain, sentiment_score, community_engagement, volume_activity
FROM nft_x_sentiment
WHERE date = (SELECT MAX(date) FROM nft_x_sentiment)
AND community_engagement >= 7
AND volume_activity < 5;
```

### Query 3: Sentiment Trend (Last 3 months)
```sql
SELECT 
    slug,
    date,
    sentiment_score,
    sentiment_category
FROM nft_x_sentiment
WHERE slug = 'claynosaurz' AND chain = 'solana'
ORDER BY date DESC
LIMIT 3;
```

### Query 4: Sentiment Distribution
```sql
SELECT 
    sentiment_category,
    COUNT(*) as count
FROM nft_x_sentiment
WHERE date = (SELECT MAX(date) FROM nft_x_sentiment)
GROUP BY sentiment_category
ORDER BY count DESC;
```

---

## Error Handling & Monitoring

### Telegram Notifications

**Success Summary:**
```
✅ X Sentiment Analysis Complete

📊 Processed: 3 collections
✔️ Successful: 3

Next: Run again in 24 hours to process next batch.
```

**Error Alert:**
```
❌ X Sentiment Analysis Error: [error details]
```

### Logging

All operations logged to:
```
app/config/logging_config.py
```

Set `LOG_LEVEL=DEBUG` for verbose output.

---

## Optimization Notes

### Rate Limiting
- 3 collections per run × 1 run per day = ~90 calls/month
- Grok typically allows 100-1000 calls/day limits
- Well within safe margins

### API Cost
- Estimated: $0.10-0.30/month (at typical Grok pricing)
- Scale up to 10+ per day if budget allows

### Database Performance
- Index on `(collection_identifier, chain, date)` optimizes queries
- UNIQUE constraint prevents duplicate entries
- Monthly data = small table size (forever)

---

## Troubleshooting

### No sentiment data appearing?

1. **Check migrations ran:**
   ```bash
   python scripts/verify_database.py
   ```

2. **Verify X handles in nft_collections:**
   ```sql
   SELECT slug, chain, x_page FROM nft_collections 
   WHERE x_page IS NOT NULL AND x_page != '' LIMIT 5;
   ```

3. **Check Grok API key:**
   ```bash
   echo $GROK_API_KEY
   ```

4. **Check collections have ranking < 100:**
   ```sql
   SELECT DISTINCT slug, chain, ranking
   FROM historical_nft_data
   WHERE ranking < 100
   LIMIT 10;
   ```

### Grok API returning empty responses?

1. Verify API key has quota
2. Check prompt format matches expected JSON
3. Add error logging:
   ```bash
   LOG_LEVEL=DEBUG python scripts/fetch_x_sentiment_grok.py
   ```

### Telegram commands not working?

1. Register handlers in `telegram_bot.py`:
   ```python
   from app.telegram.commands.x_sentiment import x_sentiment_handler, x_sentiment_top_handler
   
   application.add_handler(x_sentiment_handler)
   application.add_handler(x_sentiment_top_handler)
   ```

2. Verify user ID is in `ALLOWED_TELEGRAM_IDS`

---

## Future Enhancements

1. **Trend Analysis**: Compare sentiment month-over-month for trend detection
2. **Correlation Analysis**: Correlate sentiment with price movements
3. **Keyword Extraction**: Automatically identify emerging topics
4. **Sentiment Alerts**: Notify when sentiment drops below threshold
5. **Influence Tracking**: Monitor which influencers/accounts drive sentiment
6. **Webhook Integration**: Real-time data to companion dashboard

---

## References

- Grok API Docs: https://docs.x.ai/docs
- Twitter/X API: https://developer.twitter.com/
- SQLite Documentation: https://www.sqlite.org/docs.html
