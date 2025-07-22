from datetime import datetime
import numpy as np
from telegram import Update
from telegram.ext import ContextTypes
from app.telegram.utils.auth import is_authorized, access_denied
from app.utils.db_connection import get_db_connection
from app.utils.moving_average import calculate_sma, count_days_present

async def ma_generic(update: Update, context: ContextTypes.DEFAULT_TYPE, floor_field: str):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await access_denied(update)
        return
    
    if not context.args:
        await update.message.reply_text("Uso: /ma_native <slug> oppure /ma_usd <slug>")
        return
    slug = context.args[0]
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT collection_identifier FROM nft_collections WHERE slug=?", (slug,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Slug not found")
        conn.close()
        return
    collection_identifier = row[0]
    
    cur.execute("SELECT COUNT(*) FROM historical_nft_data WHERE collection_identifier=?", (collection_identifier,))
    collection_historical_count = cur.fetchone()[0]
    if collection_historical_count == 0:
        await update.message.reply_text("No historical data found for this slug")
        conn.close()
        return
    
    cur.execute(
        f"SELECT latest_floor_date, {floor_field}, chain FROM historical_nft_data WHERE collection_identifier=? "
        "ORDER BY latest_floor_date ASC",
        (collection_identifier,)
    )
    db_rows = cur.fetchall()
    conn.close()
    
    first_available_date = db_rows[0][0]
    slug_chain = db_rows[0][2]
    date_value_list = [(r[0], r[1]) for r in db_rows]
    today = datetime.utcnow().date()
    end_date = today.strftime("%Y-%m-%d")
    
    periods = [
        (20, 1, "SMA20"),
        (50, 3, "SMA50"),
        (100, 5, "SMA100"),
        (200, 10, "SMA200"),
    ]
    sma_results = {}
    for period, threshold, label in periods:
        value = calculate_sma(date_value_list, period, end_date, missing_threshold=threshold)
        sma_results[label] = value
    
    present, missing = count_days_present(date_value_list, 200, end_date)
    
    # Ternario corretto fuori dalla format
    sma20_text = f"{sma_results['SMA20']:.4f}" if not np.isnan(sma_results['SMA20']) else "N/A"
    sma50_text = f"{sma_results['SMA50']:.4f}" if not np.isnan(sma_results['SMA50']) else "N/A"
    sma100_text = f"{sma_results['SMA100']:.4f}" if not np.isnan(sma_results['SMA100']) else "N/A"
    sma200_text = f"{sma_results['SMA200']:.4f}" if not np.isnan(sma_results['SMA200']) else "N/A"
    
    msg_out = (
        f"{slug} : {slug_chain}, {collection_historical_count} records found\n\n"
        f"📅 Data available since: {first_available_date}\n\n"
        f"SMA20: {sma20_text}\n"
        f"SMA50: {sma50_text}\n"
        f"SMA100: {sma100_text}\n"
        f"SMA200: {sma200_text}\n\n"
        f"Days check: {present} present, {missing} missing"
    )
    await update.message.reply_text(msg_out)