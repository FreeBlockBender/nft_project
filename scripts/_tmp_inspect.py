import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.database.db_connection import get_db_connection
conn = get_db_connection()
cur = conn.cursor()

print("=== categories distribution ===")
cur.execute("SELECT categories, COUNT(*) FROM nft_collections GROUP BY categories ORDER BY COUNT(*) DESC LIMIT 30")
for r in cur.fetchall(): print(r)

print("\n=== art category samples ===")
cur.execute("SELECT slug, chain, categories FROM nft_collections WHERE categories LIKE '%art%' LIMIT 10")
for r in cur.fetchall(): print(r)

print("\n=== supply info in collections? ===")
import sqlite3
cur.execute("PRAGMA table_info(nft_collections)")
for r in cur.fetchall(): print(r)

print("\n=== supply/total_supply samples from historical_nft_data ===")
cur.execute("SELECT slug, chain, total_supply FROM historical_nft_data WHERE total_supply IS NOT NULL ORDER BY latest_floor_date DESC LIMIT 10")
for r in cur.fetchall(): print(r)

print("\n=== floor_native distribution of GC 50/200 collections ===")
cur.execute("""
    SELECT gc.floor_native
    FROM historical_golden_crosses gc
    WHERE gc.ma_short_period=50 AND gc.ma_long_period=200
      AND gc.floor_native IS NOT NULL
    ORDER BY gc.floor_native
""")
vals = [r[0] for r in cur.fetchall()]
buckets = {"0-0.1": 0, "0.1-0.3": 0, "0.3-1": 0, "1-5": 0, "5-20": 0, "20+": 0}
for v in vals:
    if v < 0.1: buckets["0-0.1"] += 1
    elif v < 0.3: buckets["0.1-0.3"] += 1
    elif v < 1: buckets["0.3-1"] += 1
    elif v < 5: buckets["1-5"] += 1
    elif v < 20: buckets["5-20"] += 1
    else: buckets["20+"] += 1
print(buckets)

conn.close()
