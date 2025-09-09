import sqlite3
from datetime import datetime, timedelta
import tweepy
from telegram.error import TelegramError
import asyncio
from concurrent.futures import ThreadPoolExecutor
import argparse
import logging
from app.config.config import load_config
from app.telegram.utils.telegram_notifier import send_telegram_message, get_gc_draft_chat_id
from app.telegram.utils.telegram_msg_templates import (
    format_golden_cross_msg,
    format_golden_cross_monthly_recap_msg
)

# Configure logging
logging.basicConfig(
    filename='golden_cross.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load configuration
config = load_config()
db_path = config.get("DB_PATH", "nft_data.sqlite3")
API_KEY = config.get("X_API_KEY")
API_SECRET_KEY = config.get("X_API_SECRET_KEY")
ACCESS_TOKEN = config.get("X_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = config.get("X_ACCESS_TOKEN_SECRET")

# ThreadPoolExecutor for X API
executor = ThreadPoolExecutor(max_workers=1)

def post_to_x(message):
    """Post a message to X."""
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET_KEY,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        if len(message) > 280:
            message = message[:277] + "..."
        client.create_tweet(text=message)
        logging.info(f"Successfully posted to X: {message[:50]}...")
        return True
    except tweepy.TweepyException as e:
        logging.error(f"Error posting to X: {e}")
        raise

def get_crosses_between_dates(conn, date_from, date_to, ma_short_period=None, ma_long_period=None):
    """Retrieve all Golden Crosses between two dates (inclusive), with optional MA filters."""
    cur = conn.cursor()
    query = """
        SELECT * FROM historical_golden_crosses
        WHERE date BETWEEN ? AND ?
    """
    params = [date_from, date_to]
    if ma_short_period is not None and ma_long_period is not None:
        query += " AND ma_short_period = ? AND ma_long_period = ?"
        params.extend([ma_short_period, ma_long_period])
    query += " ORDER BY date DESC"
    cur.execute(query, tuple(params))
    return cur.fetchall()

def get_crosses_by_date(conn, target_date):
    """Retrieve all Golden Crosses for the specified date."""
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM historical_golden_crosses
        WHERE date = ?
    """, (target_date,))
    return cur.fetchall()

def get_nftdata(conn, collection_identifier, target_date):
    """Retrieve data from historical_nft_data for a specific date."""
    cur = conn.cursor()
    cur.execute("""
        SELECT slug, ranking, floor_native, floor_usd,
               contract_address, chain, chain_currency_symbol,
               unique_owners, total_supply, listed_count, best_price_url
        FROM historical_nft_data
        WHERE collection_identifier = ? AND latest_floor_date = ?
        LIMIT 1
    """, (collection_identifier, target_date))
    return cur.fetchone()

async def notify_crosses(conn, crosses, label="periodo selezionato"):
    """Send Golden Cross notifications to Telegram and X."""
    if not crosses:
        logging.info(f"Nessuna Golden Cross trovata per il {label}.")
        return
    logging.info(f"Golden Cross trovate per {label}: {len(crosses)}")
    chat_id = get_gc_draft_chat_id()
    count_sent = 0
    loop = asyncio.get_event_loop()
    
    for cross in crosses:
        nft_data = get_nftdata(conn, cross['collection_identifier'], cross['date'])
        if nft_data:
            msg_data = {}
            for k in cross.keys():
                msg_data[f"historical_golden_crosses.{k}"] = cross[k]
                msg_data[k] = cross[k]
            for k in nft_data.keys():
                msg_data[f"historical_nft_data.{k}"] = nft_data[k]
                msg_data[k] = nft_data[k]
            
            # Telegram message
            telegram_success = False
            telegram_msg = format_golden_cross_msg(msg_data)
            try:
                result = await send_telegram_message(telegram_msg, chat_id)
                logging.info(f"Sent Telegram message for {cross['collection_identifier']}")
                telegram_success = True
            except TelegramError as e:
                logging.error(f"Error sending to Telegram for {cross['collection_identifier']}: {e}")
            except Exception as e:
                logging.error(f"Unexpected error in Telegram send for {cross['collection_identifier']}: {e}")
            
            # X message
            x_success = False
            try:
                x_msg = telegram_msg.format_golden_cross_x_msg(msg_data)
                await loop.run_in_executor(executor, post_to_x, x_msg)
                x_success = True
            except Exception as e:
                logging.error(f"Error sending to X for {cross['collection_identifier']}: {e}")
            
            if telegram_success or x_success:
                count_sent += 1
    
    logging.info(f"Inviati {count_sent} messaggi Golden Cross su Telegram e/o X ({label}).")

async def notify_today_crosses(conn):
    """Notify today's Golden Crosses on Telegram and X."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    crosses = get_crosses_by_date(conn, today)
    await notify_crosses(conn, crosses, label="data odierna")

async def notify_crosses_for_date(conn, target_date):
    """Notify Golden Crosses for a specific date on Telegram and X."""
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
        crosses = get_crosses_by_date(conn, target_date)
        await notify_crosses(conn, crosses, label=f"data {target_date}")
    except ValueError:
        logging.error(f"Invalid date format: {target_date}. Use YYYY-MM-DD.")

async def notify_monthly_crosses(conn, days=365, ma_short_period=None, ma_long_period=None):
    """Send a single monthly recap message of all Golden Crosses to Telegram and X."""
    today = datetime.utcnow().date()
    from_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")
    crosses = get_crosses_between_dates(
        conn, from_date, to_date, ma_short_period=ma_short_period, ma_long_period=ma_long_period
    )

    unified_data = []
    for cross in crosses:
        collection_identifier = cross["collection_identifier"]
        cross_date = cross["date"]
        is_native = cross["is_native"]
        nft_row = get_nftdata(conn, collection_identifier, cross_date)
        if not nft_row:
            continue
        cur = conn.cursor()
        cur.execute(
            "SELECT floor_native, floor_usd, chain_currency_symbol, latest_floor_date "
            "FROM historical_nft_data WHERE collection_identifier = ? ORDER BY latest_floor_date DESC LIMIT 1",
            (collection_identifier,)
        )
        current_nft_row = cur.fetchone()
        if not current_nft_row:
            continue

        item = {
            "slug": nft_row["slug"],
            "chain": nft_row["chain"],
            "is_native": is_native,
            "chain_currency_symbol": nft_row["chain_currency_symbol"],
            "floor_native": cross["floor_native"],
            "floor_usd": cross["floor_usd"],
            "date": cross_date,
            "current_floor_native": current_nft_row["floor_native"],
            "current_floor_usd": current_nft_row["floor_usd"]
        }
        unified_data.append(item)

    today_str = today.strftime("%d-%m-%Y")
    ma1 = ma_short_period if ma_short_period is not None else "?"
    ma2 = ma_long_period if ma_long_period is not None else "?"
    msg = format_golden_cross_monthly_recap_msg(unified_data, ma1, ma2, today_str)
    chat_id = get_gc_draft_chat_id()
    
    try:
        await send_telegram_message(msg, chat_id)
        logging.info("Sent monthly recap to Telegram")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, post_to_x, msg)
        logging.info("Sent monthly recap to X")
    except TelegramError as e:
        logging.error(f"Error sending monthly recap to Telegram: {e}")
    except Exception as e:
        logging.error(f"Error sending monthly recap to X: {e}")

async def main():
    """Main function to run the notification process for a specific date."""
    parser = argparse.ArgumentParser(description="Notify Golden Crosses for a specific date.")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.utcnow().strftime("%Y-%m-%d"),
        help="Date for Golden Cross notifications (YYYY-MM-DD). Defaults to today."
    )
    args = parser.parse_args()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        await notify_crosses_for_date(conn, args.date)
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(main())