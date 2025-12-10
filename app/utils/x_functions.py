import tweepy
import logging
from app.config.config import load_config
import random
from datetime import datetime
config = load_config()

API_KEY = config.get("X_API_KEY")
API_SECRET_KEY = config.get("X_API_SECRET_KEY")
ACCESS_TOKEN = config.get("X_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = config.get("X_ACCESS_TOKEN_SECRET")

def post_to_x(message):
    """Post a message to X."""
    try:
        client = tweepy.Client(
            consumer_key=API_KEY,
            consumer_secret=API_SECRET_KEY,
            access_token=ACCESS_TOKEN,
            access_token_secret=ACCESS_TOKEN_SECRET
        )
        client.create_tweet(text=message)
        logging.info(f"Successfully posted to X: {message[:50]}...")
        return True
    except tweepy.TweepyException as e:
        logging.error(f"Error posting to X: {e}")
        raise


def format_golden_cross_x_msg(obj) -> str:
    """
    Create a concise Golden Cross message for X.
    Rounds floor_native to 4 decimals, floor_usd to 2 decimals, MA short/long to 4 decimals.
    Uses dynamic MA periods and appropriate currency suffix.
    """
    floor_native = f"{obj.get('floor_native', 0):.4f}" if obj.get('floor_native') is not None else "N/A"
    floor_usd = f"{obj.get('floor_usd', 0):.2f}" if obj.get('floor_usd') is not None else "N/A"
    ma_short = f"{obj.get('ma_short', 0):.4f}" if obj.get('ma_short') is not None else "N/A"
    ma_long = f"{obj.get('ma_long', 0):.4f}" if obj.get('ma_long') is not None else "N/A"

    # Dynamic MA periods
    period_short = obj.get('ma_short_period', "short")
    period_long = obj.get('ma_long_period', "long")

    # Currency suffix for MA
    currency = obj.get('chain_currency_symbol', '') if obj.get('is_native', 1) in (1, "1", True) else "USD"

    # Currency suffix for floor price
    currency_floor = obj.get('chain_currency_symbol', '') 

    # Collection slug for mention and hashtag
    slug = obj.get('slug', 'Unknown')
    collection_name = obj.get('name', slug)
    x_handle = obj.get('x_page', None)
    slug_mention = f"{x_handle}" if x_handle is not None else slug

    # Safe hashtag generation, removing spaces and hyphens
    hashtag_name = collection_name.replace(' ', '').replace('-', '') if isinstance(collection_name, str) else 'Unknown'

    cta_phrases = [
        "Snag one here",
        "Check it out",
        "Grab yours now",
        "Dive in here",
        "Explore now"
    ]

    cta_phrase = random.choice(cta_phrases)

    # Construct the message
    msg = (
        f"🚨 GOLDEN CROSS ALERT! 🚀\n\n"
        f"{collection_name} by {slug_mention} NFTs on #{obj.get('chain', 'N/A')} are BULLISH!\n\n"
        f"📈 MA{period_short} ({ma_short} {currency}) > MA{period_long} ({ma_long} {currency}).\n"
        f"Floor: {floor_native} {currency_floor} (~${floor_usd})."
        f"{obj.get('total_supply', 'N/A')} supply, {obj.get('unique_owners', 'N/A')} owners, {obj.get('listed_count', 'N/A')} listed.\n\n"
        f"#NFTs #{hashtag_name} \n\n"
        f"{cta_phrase}: {obj.get('best_price_url')}" if obj.get('best_price_url') is not None else ""
    )

    return msg


def format_marketing_x_post():
    hooks = [
        "Your NFT just 5x’d — when do you sell?",
        "Golden Cross just hit a top collection.",
        "Death Cross forming… still holding?",
        "Bags up 800%. Now what?",
        "Most sell too early. Smart ones use data.",
        "This pump still has legs?",
    ]

    value = [
        "@NFTalertX – free pro tools:\n• Live Golden/Death Cross alerts\n• Instant MA charts (20-200 DMA)\n• Real-time sell signals",
        "Free signals + charts at @NFTalertX:\n• Golden & Death Crosses\n• Moving averages on demand\n• Know exactly when to take profits",
        "@NFTalertX gives you:\n• Live technical alerts\n• Pro charts in seconds\n• Stop guessing, start managing",
    ]

    cta = [
        "Join free → https://t.me/NFTAlertXComm",
        "Data > FOMO → https://t.me/NFTAlertXComm",
        "Free charts & signals → https://t.me/NFTAlertXComm",
        "Stop hoping, start winning → https://t.me/NFTAlertXComm",
    ]

    emojis = ["📈", "🚀", "🔷", "📊", "🔥", "💎", "⚡", "👇"]

    post = (
        random.choice(hooks) + "\n\n" +
        random.choice(value) + "\n\n" +
        random.choice(cta) + "\n\n" +
        " ".join(random.sample(emojis, k=random.randint(3,5)))
    )
    return post