# NFT Golden Cross Signal Bot

This project identifies **Golden Cross** patterns in NFT collection price data and sends alerts via a private Telegram bot. It is built in **Python** with an **SQLite** database for data storage and supports modular execution via scripts.

---

## 📊 What is a Golden Cross?

A **Golden Cross** is a bullish technical analysis pattern that occurs when a short-term moving average (e.g., 50-day MA) crosses above a long-term moving average (e.g., 200-day MA).  
In this project, the pattern is applied to price data from NFT collections.

---

## 📁 Project Structure

✅ Versioned
⛔️ Not Versioned

```bash
nft_project/
│   .env ⛔️ Environment variables               
│   .gitignore ✅
│   main.py ✅ App entry point (currently unused)
│   nft_data.sqlite3 ⛔️ Database
│   README.md ✅
│
├───app ✅
│   │   config.py ✅ Loads and returns all configuration variables from the .env file.
│   │   database.py ✅ Initializes the database and tables if needed, and returns an active connection.
│   │   __init__.py ✅
│   │
│   ├───data_import ✅
│   │   │   import_api.py ✅ Imports NFT data via API, stores it in the database, and saves the response.
│   │   │   import_collections.py ✅ Detects and imports updated collection metadata since the previous day.
│   │   │   import_csv.py ✅ Imports historical floor data from CSV files.
│   │   │   __init__.py ✅
│   │
│   ├───utils ✅
│   │   │   helpers.py ✅ A set of generic helper functions.
│   │   │   logging_config.py ✅ Global logging configuration with timestamps, reusable across all files.
│   │   │   moving_average.py ✅ Implements a function to calculate the SMA and verify continuity of days.
│   │   │   telegram_bot.py ✅ Implements the Telegram bot and its commands.
│   │   │   telegram_msg_templates.py ✅ Centralizes Telegram message templates.
│   │   │   telegram_notifier.py ✅ Used to send a Telegram message to the specified chat_id.
│   │   │   __init__.py ✅
│   
│
├───data ✅
│   │
│   └───nft_historical_data ✅ Repository for CSV files containing historical floor prices.
│
├───doc ✅
│       Deploy NFT project.docx ✅ Project technical specification (firs draft).
│
├───scripts ✅
│   │   create_database.py ✅ Script to initialize NFT database tables.
│   │   import_api_data.py ✅ Script to import NFT historical data via API.
│   │   import_collections_data.py ✅ Script to import NFT metadata.
│   │   import_csv_files.py ✅ Script to import CSV historical data.
│   │   verify_database.py ✅ Script to verify database tables.
│
└───tests ✅
        __init__.py ✅
```

✍ None of the pycache directories are included in version control, for obvious reasons.

---

## 🤖 Telegram bot commands

| Command               | Description                                                      |
|-----------------------|------------------------------------------------------------------|
| `vibes`               | 🎨 Mostra il social hype e sentiment attuale del mercato NFT (Grok AI). |
| `import_vibes`        | 🔄 Genera nuovi dati di social hype usando l'API di Grok.        |
| `check_daily_insert`  | Verifies the number of today's inserts in `historical_nft_data`. |
| `slug_list_by_prefix` | Retrieves collection slugs that start with a specific prefix.     |
| `slug_list_by_chain`  | Lists slugs filtered by the related blockchain.                  |
| `slug_list_by_category` | Finds slugs organized by category.                             |
| `meta`                | Fetches detailed metadata for an NFT collection.                 |
| `ma_native`           | Displays moving averages for the collection in native currency.  |
| `ma_usd`             | Displays moving averages for the collection in USD.              |

---

## 🎨 NFT Social Hype (Powered by Grok AI)

New feature per misurare il "vibe" generale del mercato NFT usando l'API di Grok. Analizza il sentiment della comunità crypto e fornisce score di hype in tempo reale.

**Configurazione rapida:**
1. Aggiungi `GROK_API_KEY` al `.env`
2. Esegui `/import_vibes` per generare i dati
3. Usa `/vibes` per vedere il sentiment attuale

📖 Per dettagli completi: vedi [doc/SOCIAL_HYPE_SETUP.md](doc/SOCIAL_HYPE_SETUP.md)

---

## 🔧 Git Workflow Guide

All development must be done on the `develop` branch.  
The `master` branch should only contain stable, production-ready code.

### 📥 Clone the Repository

```bash
git clone https://github.com/FreeBlockBender/nft_project.git
cd nft-golden-cross-bot
```

### 🔄 Update the Local Repository
```bash
git pull origin develop
```

### 🌿 Switch to the Develop Branch
```bash
git checkout develop
```

### 🧑‍💻 Create a New Feature Branch
```bash
git checkout -b feature/your-feature-name
```

After implementing your changes:
```bash
git add .
git commit -m "Describe your changes here"
git push origin feature/your-feature-name
```

### 🔀 Open a Pull Request

- Push your changes to your feature branch.
- Go to the GitHub repository.
- Open a *Pull Request* from `feature/your-feature-name` → `develop`.
- Once changes are reviewed and tested, a second *Pull Request* should be opened from `develop` → `master` to deploy to production.

✅ Summary

- Develop only on develop
- Never commit directly to master
- Use feature branches for clarity and isolation
- Pull Request flow: feature → develop → master


## 🤖 Script list

| Script                | Description                                                      |
|-----------------------|------------------------------------------------------------------|
| `scripts.detect_current_golden_crosses_20_50`  | Verifies the number of today's inserts in `historical_nft_data`. |
| `slug_list_by_prefix` | Retrieves collection slugs that start with a specific prefix.     |
| `slug_list_by_chain`  | Lists slugs filtered by the related blockchain.                  |
| `slug_list_by_category` | Finds slugs organized by category.                             |
| `meta`                | Fetches detailed metadata for an NFT collection.                 |
| `ma_native`           | Displays moving averages for the collection in native currency.  |
| `ma_usd`             | Displays moving averages for the collection in USD.              |

Tabelle database:

CREATE TABLE "historical_nft_data" (
    collection_identifier TEXT,
    contract_address TEXT,
    slug TEXT,
    latest_floor_date TEXT,
    latest_floor_timestamp TEXT,
    floor_native REAL,
    floor_usd REAL,
    chain TEXT,
    chain_currency_symbol TEXT,
    marketplace_source TEXT,
    ranking INTEGER,
    unique_owners INTEGER,
    total_supply INTEGER,
    listed_count INTEGER,
    best_price_url TEXT,
    sale_count_24h INTEGER,
    sale_volume_native_24h REAL,
    highest_sale_native_24h REAL,
    lowest_sale_native_24h REAL,
    PRIMARY KEY (slug, chain, latest_floor_date)
)


CREATE TABLE "historical_golden_crosses" (
    slug TEXT,
    chain TEXT,
    date TEXT,
    inserted_ts TEXT,
    is_native INTEGER,
    floor_native REAL,
    floor_usd REAL,
    ma_short REAL,
    ma_long REAL,
    ma_short_previous_day REAL,
    ma_long_previous_day REAL,
    ma_short_period INTEGER,
    ma_long_period INTEGER, telegram_sent INTEGER DEFAULT 0, x_sent INTEGER DEFAULT 0,
    PRIMARY KEY (date, slug, chain, ma_short_period, ma_long_period)
)


CREATE TABLE "nft_collections" (
	"id"	INTEGER,
	"collection_identifier"	TEXT,
	"contract_address"	TEXT,
	"slug"	TEXT,
	"name"	TEXT,
	"chain"	TEXT,
	"chain_currency_symbol"	TEXT,
	"categories"	TEXT,
	"x_page"	TEXT,
	"marketplace_url"	TEXT,
	PRIMARY KEY("id" AUTOINCREMENT)
)