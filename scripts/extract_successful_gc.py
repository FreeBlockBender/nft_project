import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.config.logging_config import setup_logging
import logging
import sqlite3
from app.config.config import load_config
from app.database.db_connection import get_db_connection
import csv

def main():
    setup_logging()
    logging.info("Starting extraction of successful golden crosses...")

    config = load_config()
    db_path = config.get("DB_PATH", "nft_data.sqlite3")

    conn = get_db_connection()
    cur = conn.cursor()

    # Query to get golden crosses with entry (gc_date +7d) and exits (+30d, +60d from gc_date)
    query = """
    SELECT gc.slug, gc.chain, gc.date as gc_date,
           gc.floor_native as gc_price_native, gc.floor_usd as gc_price_usd,
           h1.floor_native as entry_price_native, h1.floor_usd as entry_price_usd,
           h2.floor_native as exit_price_native_30d, h2.floor_usd as exit_price_usd_30d,
           h3.floor_native as exit_price_native_60d, h3.floor_usd as exit_price_usd_60d
    FROM historical_golden_crosses gc
    LEFT JOIN historical_nft_data h1 ON h1.slug = gc.slug
                                     AND h1.chain = gc.chain
                                     AND h1.latest_floor_date = date(gc.date, '+7 days')
    LEFT JOIN historical_nft_data h2 ON h2.slug = gc.slug
                                     AND h2.chain = gc.chain
                                     AND h2.latest_floor_date = date(gc.date, '+37 days')
    LEFT JOIN historical_nft_data h3 ON h3.slug = gc.slug
                                     AND h3.chain = gc.chain
                                     AND h3.latest_floor_date = date(gc.date, '+67 days')
    WHERE gc.ma_short_period = 50 AND gc.ma_long_period = 200
    AND h1.latest_floor_date IS NOT NULL
    """

    cur.execute(query)
    rows = cur.fetchall()

    logging.info(f"Fetched {len(rows)} golden cross records from DB.")

    successful_gc = []

    for row in rows:
        slug, chain, gc_date, gc_native, gc_usd, entry_native, entry_usd, exit_native_30, exit_usd_30, exit_native_60, exit_usd_60 = row

        # Calculate returns for 30d hold
        ret_30_native = None
        ret_30_usd = None
        if exit_native_30 and entry_native:
            ret_30_native = (exit_native_30 - entry_native) / entry_native * 100
        if exit_usd_30 and entry_usd:
            ret_30_usd = (exit_usd_30 - entry_usd) / entry_usd * 100

        # For 60d hold
        ret_60_native = None
        ret_60_usd = None
        if exit_native_60 and entry_native:
            ret_60_native = (exit_native_60 - entry_native) / entry_native * 100
        if exit_usd_60 and entry_usd:
            ret_60_usd = (exit_usd_60 - entry_usd) / entry_usd * 100

        # Check if profitable in native (primary)
        profitable_30 = ret_30_native and ret_30_native > 0
        profitable_60 = ret_60_native and ret_60_native > 0

        if profitable_30 or profitable_60:
            successful_gc.append({
                'slug': slug,
                'chain': chain,
                'gc_date': gc_date,
                'entry_date': f"{gc_date} +7d",
                'entry_price_native': entry_native,
                'exit_30d_price_native': exit_native_30,
                'return_30d_native_%': ret_30_native,
                'exit_60d_price_native': exit_native_60,
                'return_60d_native_%': ret_60_native,
                'profitable_30d': profitable_30,
                'profitable_60d': profitable_60
            })

    conn.close()

    logging.info(f"Found {len(successful_gc)} successful golden crosses.")

    # Print or save results
    if successful_gc:
        print(f"Found {len(successful_gc)} successful golden crosses. Saving to successful_gc.csv")
        with open('successful_gc.csv', 'w', newline='') as csvfile:
            fieldnames = ['slug', 'chain', 'gc_date', 'entry_date', 'entry_price_native', 'exit_30d_price_native', 'return_30d_native_%', 'exit_60d_price_native', 'return_60d_native_%', 'profitable_30d', 'profitable_60d']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for gc in successful_gc:
                writer.writerow(gc)
    else:
        print("No successful golden crosses found with the given criteria.")

    logging.info("Extraction complete.")

if __name__ == "__main__":
    main()