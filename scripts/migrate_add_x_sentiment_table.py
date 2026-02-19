#!/usr/bin/env python3
"""
Migration script to add x_sentiment table for tracking per-collection X sentiment.
Tracks sentiment history for top 100 collections on a monthly basis.
"""

import sqlite3
from app.config.logging_config import setup_logging
from app.database.db_connection import get_db_connection
import logging

def migrate_add_x_sentiment_table():
    """Add nft_x_sentiment table and x_page column to nft_collections."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Add x_page column to nft_collections if it doesn't exist
        logger.info("Checking if x_page column exists in nft_collections...")
        cursor.execute("PRAGMA table_info(nft_collections)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'x_page' not in columns:
            logger.info("Adding x_page column to nft_collections...")
            cursor.execute("""
                ALTER TABLE nft_collections ADD COLUMN x_page TEXT DEFAULT NULL;
            """)
            logger.info("x_page column added successfully.")
        else:
            logger.info("x_page column already exists.")
        
        # Create nft_x_sentiment table
        logger.info("Creating nft_x_sentiment table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS nft_x_sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_identifier TEXT,
            slug TEXT,
            chain TEXT,
            date TEXT,
            timestamp TEXT,
            sentiment_score INTEGER,
            sentiment_category TEXT,
            bullish_indicators TEXT,
            bearish_indicators TEXT,
            key_topics TEXT,
            community_engagement TEXT,
            volume_activity TEXT,
            raw_grok_response TEXT,
            created_at TEXT,
            UNIQUE(collection_identifier, chain, date)
        );
        """)
        logger.info("nft_x_sentiment table created successfully.")
        
        # Create index for efficient querying
        logger.info("Creating index on nft_x_sentiment...")
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_x_sentiment_collection_date 
        ON nft_x_sentiment (collection_identifier, chain, date DESC);
        """)
        logger.info("Index created successfully.")
        
        # Create table to track last update for monthly scheduling
        logger.info("Creating nft_x_sentiment_schedule table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS nft_x_sentiment_schedule (
            collection_identifier TEXT PRIMARY KEY,
            slug TEXT,
            chain TEXT,
            last_updated_date TEXT,
            last_grok_call TEXT,
            status TEXT
        );
        """)
        logger.info("nft_x_sentiment_schedule table created successfully.")
        
        conn.commit()
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_add_x_sentiment_table()
