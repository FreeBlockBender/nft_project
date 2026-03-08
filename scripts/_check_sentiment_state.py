import sqlite3
import os
from datetime import datetime, timedelta

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'nft_data.sqlite3')
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM nft_x_sentiment")
print("Total rows in nft_x_sentiment:", cur.fetchone()[0])

cur.execute("SELECT COUNT(DISTINCT slug || chain) FROM nft_x_sentiment")
print("Distinct collections processed (by slug+chain):", cur.fetchone()[0])

# Fixed query (same as fetch_collections_needing_update)
cur.execute("""
WITH latest_dates AS (
    SELECT collection_identifier, chain, MAX(latest_floor_date) AS max_date
    FROM historical_nft_data
    GROUP BY collection_identifier, chain
),
latest_data AS (
    SELECT h.collection_identifier, h.slug, h.chain, h.ranking
    FROM historical_nft_data h
    JOIN latest_dates ld
        ON h.collection_identifier = ld.collection_identifier
        AND h.chain = ld.chain
        AND h.latest_floor_date = ld.max_date
    WHERE h.ranking <= 100 AND h.ranking IS NOT NULL
),
best_per_slug AS (
    SELECT slug, chain, MIN(ranking) AS best_ranking
    FROM latest_data
    GROUP BY slug, chain
),
canonical AS (
    SELECT ld.collection_identifier, ld.slug, ld.chain, ld.ranking
    FROM latest_data ld
    JOIN best_per_slug bp
        ON ld.slug = bp.slug AND ld.chain = bp.chain AND ld.ranking = bp.best_ranking
    GROUP BY ld.slug, ld.chain
),
unique_nc AS (
    SELECT slug, chain, MAX(x_page) AS x_page
    FROM nft_collections
    WHERE x_page IS NOT NULL AND x_page != ''
    GROUP BY slug, chain
)
SELECT c.collection_identifier, c.slug, c.chain, nc.x_page, c.ranking
FROM canonical c
JOIN unique_nc nc ON c.slug = nc.slug AND c.chain = nc.chain
ORDER BY c.ranking ASC
LIMIT 100
""")
top_collections = cur.fetchall()
print("Unique top-100 eligible collections (after dedup):", len(top_collections))

thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
needs_update = []
already_done = []
for collection_id, slug, chain, x_page, ranking in top_collections:
    cur.execute("SELECT date FROM nft_x_sentiment WHERE slug = ? AND chain = ? ORDER BY date DESC LIMIT 1", (slug, chain))
    result = cur.fetchone()
    last_date = result[0] if result else None
    if not last_date or last_date < thirty_days_ago:
        needs_update.append((ranking, slug, chain, x_page, last_date))
    else:
        already_done.append((ranking, slug, chain, last_date))

print(f"\nAlready processed and up-to-date ({len(already_done)}):")
for r in already_done:
    print(f"  rank={r[0]}, slug={r[1]}, chain={r[2]}, last={r[3]}")

print(f"\nStill needs processing ({len(needs_update)}):")
for r in needs_update:
    print(f"  rank={r[0]}, slug={r[1]}, chain={r[2]}, x={r[3]}, last={r[4]}")

conn.close()

