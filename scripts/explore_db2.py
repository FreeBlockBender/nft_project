import sqlite3

DB_PATH = r"c:\Users\Lenovo\Desktop\nft\nft_project\nft_data.sqlite3"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check golden crosses data
print("=== GOLDEN CROSSES SAMPLE ===")
cursor.execute("SELECT * FROM historical_golden_crosses LIMIT 5")
cols = [d[0] for d in cursor.description]
print("Columns:", cols)
for row in cursor.fetchall():
    print(dict(zip(cols, row)))

print("\n=== DATE RANGE for golden crosses ===")
cursor.execute("SELECT MIN(date), MAX(date) FROM historical_golden_crosses")
print(cursor.fetchone())

print("\n=== MA periods used ===")
cursor.execute("SELECT DISTINCT ma_short_period, ma_long_period FROM historical_golden_crosses")
print(cursor.fetchall())

print("\n=== NFT DATA SAMPLE ===")
cursor.execute("SELECT * FROM historical_nft_data LIMIT 3")
cols2 = [d[0] for d in cursor.description]
print("Columns:", cols2)
for row in cursor.fetchall():
    print(dict(zip(cols2, row)))

print("\n=== DATE RANGE for nft_data ===")
cursor.execute("SELECT MIN(latest_floor_date), MAX(latest_floor_date) FROM historical_nft_data")
print(cursor.fetchone())

print("\n=== How golden crosses link to nft_data ===")
# Check if slug / collection_identifier matches
cursor.execute("""
    SELECT gc.slug, gc.chain, gc.date, gc.floor_usd, gc.ma_short, gc.ma_long
    FROM historical_golden_crosses gc
    ORDER BY gc.date DESC
    LIMIT 10
""")
print("\nRecent golden crosses:")
for row in cursor.fetchall():
    print(f"  slug={row[0]}, chain={row[1]}, date={row[2]}, floor_usd={row[3]}, ma50={row[4]:.4f}, ma200={row[5]:.4f}")

# Check if we can join on slug
cursor.execute("""
    SELECT gc.slug, gc.date, 
           nft.latest_floor_date, nft.floor_usd as nft_floor_usd, gc.floor_usd as gc_floor_usd
    FROM historical_golden_crosses gc
    JOIN historical_nft_data nft ON gc.slug = nft.slug AND nft.latest_floor_date = gc.date
    LIMIT 5
""")
print("\n=== JOIN test (slug + date) ===")
for row in cursor.fetchall():
    print(row)

# Check collection_identifier join
cursor.execute("""
    SELECT gc.slug, gc.date, 
           nft.latest_floor_date, nft.floor_usd, nft.collection_identifier
    FROM historical_golden_crosses gc
    JOIN historical_nft_data nft ON nft.collection_identifier = gc.slug AND nft.latest_floor_date = gc.date
    LIMIT 5
""")
print("\n=== JOIN test (collection_identifier + date) ===")
for row in cursor.fetchall():
    print(row)

# Check what identifiers look like in both tables
cursor.execute("SELECT DISTINCT slug FROM historical_golden_crosses LIMIT 10")
gc_slugs = [r[0] for r in cursor.fetchall()]
print("\n=== GC slugs sample ===", gc_slugs)

cursor.execute("SELECT DISTINCT slug FROM historical_nft_data LIMIT 10")
nft_slugs = [r[0] for r in cursor.fetchall()]
print("\n=== NFT slugs sample ===", nft_slugs)

# Check overlap
cursor.execute("""
    SELECT COUNT(DISTINCT gc.slug) 
    FROM historical_golden_crosses gc
    WHERE EXISTS (SELECT 1 FROM historical_nft_data nft WHERE nft.slug = gc.slug)
""")
print("\n=== GC slugs that exist in nft_data ===", cursor.fetchone()[0])

cursor.execute("SELECT COUNT(DISTINCT slug) FROM historical_golden_crosses")
print("Total distinct GC slugs:", cursor.fetchone()[0])

conn.close()
