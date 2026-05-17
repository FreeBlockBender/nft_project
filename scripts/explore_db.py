import sqlite3

DB_PATH = r"c:\Users\Lenovo\Desktop\nft\nft_project\nft_data.sqlite3"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("=== TABLES ===")
for t in tables:
    print(f"  {t[0]}")

# Show schema for each table
print("\n=== SCHEMAS ===")
for t in tables:
    tname = t[0]
    cursor.execute(f"PRAGMA table_info('{tname}')")
    cols = cursor.fetchall()
    print(f"\n--- {tname} ({len(cols)} columns) ---")
    for c in cols:
        print(f"  {c[1]} ({c[2]})")
    
    # Row count
    cursor.execute(f"SELECT COUNT(*) FROM '{tname}'")
    count = cursor.fetchone()[0]
    print(f"  >> {count} rows")
    
    # Sample row
    cursor.execute(f"SELECT * FROM '{tname}' LIMIT 2")
    samples = cursor.fetchall()
    if samples:
        print(f"  >> Sample: {samples[0][:8]}...")

conn.close()
