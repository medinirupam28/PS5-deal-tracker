# PS5 Deal Tracker — India (Digital & Multi-Retailer Physical)

A personal PlayStation 5 deal monitoring system for India (`en-in` region, INR prices). It monitors digital games directly on the Indian PlayStation Store and tracks physical game discs across authorized Indian retailers.

---

## Features

- **Indian PlayStation Store (`en-in`)**: Tracks live INR prices from display price text. Strictly prohibits USD conversions.
- **Edition Disambiguation & F2P Protection**: Intelligently resolves concept and product URLs. Never mistakenly tracks a ₹0 demo, trial, or free-to-play package (such as Warzone) when a paid game is intended.
- **Dynamic, Expandable Watchlist**: Add, view, edit target prices, pause, resume, or soft-remove games via the `manage_watchlist.py` CLI without editing Python source code.
- **Multi-Retailer Physical Disc Tracking**: Pluggable provider architecture for Indian retailers:
  1. Amazon India (`amazon.in`) — 6h checks, PA-API 5.0 integration.
  2. Flipkart (`flipkart.com`) — 6h checks, Partner API integration.
  3. Games The Shop (`gamestheshop.com`) — 12h checks.
  4. Games Shop India (`gamesshop.in`) — 12h checks.
  5. PlayHQ Games (`playhq.games`) — 12h checks.
- **Zero Mock Prices & Strict Compliance**: Prohibits unauthorized web scraping, bot bypass, and CAPTCHA solving. Retailers requiring official credentials report status transparently and are never assigned fake prices.
- **Dual-Backend Database with Safe Neon Migration**: Runs seamlessly on local SQLite (`ps5_deals.db`) or cloud Neon PostgreSQL (`NEON_DATABASE_URL`). An atomic migration script with row-count verification preserves all existing games, prices, and alerts.
- **Telegram Notifications**: Real-time markdown alerts for target price hits, discounts (30%+ digital, 20%+ physical), and new historical lows with duplicate alert suppression.
- **Cloud Automation via GitHub Actions**: Scheduled 2-hour digital store workflows and 6-hour physical disc workflows with concurrency locks and Telegram failure reporting.

---

## Project Structure

```
PS5DealTracker_completed/
├── .github/workflows/
│   ├── digital_monitor.yml        # Digital monitoring every 2h
│   └── physical_monitor.yml       # Physical monitoring every 6h
├── analyzer/
│   └── deal_detector.py           # Digital & physical deal & low price detector
├── collector/
│   ├── apish_collector.py         # PlayStation Store collector with edition resolver
│   └── retailers/
│       ├── base.py                # BaseRetailerProvider & RetailerPriceResult
│       ├── amazon_in.py           # Amazon India integration (PA-API 5.0)
│       ├── flipkart.py            # Flipkart integration
│       ├── games_the_shop.py      # Games The Shop integration
│       ├── games_shop_in.py       # Games Shop India integration
│       ├── playhq_games.py        # PlayHQ Games integration
│       └── registry.py            # Retailer registry & dispatcher
├── database/
│   ├── db.py                      # Unified DB layer (Neon PostgreSQL + SQLite)
│   └── migrate_to_neon.py         # Atomic SQLite -> Neon migration script
├── notifications/
│   └── telegram.py                # Formatted Markdown deal notifications
├── scheduler/
│   └── schedule.py                # Continuous scheduler
├── tests/
│   ├── test_stage1_config_db.py
│   ├── test_stage2_migration.py
│   ├── test_stage3_collector.py
│   ├── test_stage4_watchlist_cli.py
│   └── test_stage5_physical_and_telegram.py
├── .env.example                   # Template for secrets
├── .gitignore                     # Git ignore rules
├── config.py                      # Secure configuration loader
├── main.py                        # Digital monitor entry point
├── manage_watchlist.py            # Watchlist management CLI
├── monitor_physical.py            # Physical disc monitor entry point
├── ps5_deals.db                   # Local SQLite database (backup preserved)
├── requirements.txt               # Dependencies
└── watchlist.json                 # Initial configuration & fallback
```

---

## Quick Setup (Windows)

1. **Install Python 3.11+**
2. **Install Dependencies**:
   ```powershell
   py -m pip install -r requirements.txt
   ```
3. **Configure Environment**:
   Copy `.env.example` to `.env` and fill in your keys:
   ```powershell
   Copy-Item .env.example .env
   ```
   Required variables in `.env`:
   - `APISH_KEY`: API.SH key for PlayStation Store data.
   - `TELEGRAM_BOT_TOKEN`: Telegram bot token from @BotFather.
   - `TELEGRAM_CHAT_ID`: Telegram chat ID to receive deal alerts.
   - `NEON_DATABASE_URL`: (Optional) PostgreSQL connection URL for Neon cloud database.

---

## Watchlist Management CLI (`manage_watchlist.py`)

Manage your tracked games dynamically without editing Python files:

### Digital Games

- **Add a digital game** by its PlayStation Store URL:
  ```powershell
  py manage_watchlist.py add "https://store.playstation.com/en-in/concept/10002456"
  ```
  *Features automatic edition inspection, free-to-play protection, edition picker, target price prompt, and duplicate detection.*

- **Non-interactive / Scripted addition**:
  ```powershell
  py manage_watchlist.py add "https://store.playstation.com/en-in/product/EP9000-PPSA03208_00-GHOSTDIRECTORPS5" --target 2500 -y
  ```

- **List all tracked digital games**:
  ```powershell
  py manage_watchlist.py list
  ```

- **Update target price**:
  ```powershell
  py manage_watchlist.py target 2 1499
  ```

- **Pause or Resume monitoring** (preserves all historical prices & settings):
  ```powershell
  py manage_watchlist.py toggle 2 --disable   # Pauses monitoring
  py manage_watchlist.py toggle 2 --enable    # Resumes monitoring
  ```

- **Remove from monitoring** (soft removal; historical records are never deleted):
  ```powershell
  py manage_watchlist.py remove 2 -y
  ```

- **Export & Import Watchlist**:
  ```powershell
  py manage_watchlist.py export --output my_watchlist.json
  py manage_watchlist.py import my_watchlist.json
  ```

### Physical Disc Games

- **View retailer integration statuses**:
  ```powershell
  py manage_watchlist.py retailers
  ```

- **Add a physical game**:
  ```powershell
  py manage_watchlist.py add-physical "Marvel's Spider-Man 2" --edition "Standard" --target 3500 --url "https://www.amazon.in/dp/B0CL5KMQ6P"
  ```

- **Link additional retailer listings** to an existing game:
  ```powershell
  py manage_watchlist.py add-listing 1 "https://www.gamestheshop.com/..." --retailer games_the_shop
  ```

- **List all physical game listings**:
  ```powershell
  py manage_watchlist.py list-physical
  ```

---

## Running Monitors

### 1. Digital Game Monitoring

- **Run once** (ideal for CI/CD or manual check):
  ```powershell
  py main.py --once
  ```

- **Run continuously** (checks every 2 hours while running):
  ```powershell
  py main.py
  ```

### 2. Physical Disc Monitoring

- **Run physical monitoring cycle**:
  ```powershell
  py monitor_physical.py
  ```

---

## Database Migration to Neon PostgreSQL

To migrate your existing SQLite database (`ps5_deals.db`) to Neon PostgreSQL:

1. Add your Neon PostgreSQL URL to `.env` (or pass via `--neon-url`):
   ```env
   NEON_DATABASE_URL=postgresql://user:password@ep-sample-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
2. **Run Dry Run (Optional verification)**:
   ```powershell
   py database/migrate_to_neon.py --dry-run
   ```
3. **Execute Migration**:
   ```powershell
   py database/migrate_to_neon.py
   ```

**Safety Guarantees**:
- A timestamped backup copy is automatically created in `backups/ps5_deals_backup_<timestamp>.db`.
- The original `ps5_deals.db` is never deleted or modified.
- All records (games, price_history, watchlist, alerts, retailers) are transferred in an atomic transaction.
- Verifies exact record counts match before committing; rolls back immediately if any count fails.

---

## Cloud Automation (GitHub Actions)

Two GitHub Actions workflows are provided in `.github/workflows/`:
1. `digital_monitor.yml`: Runs every 2 hours (`0 */2 * * *`) and on manual trigger (`workflow_dispatch`).
2. `physical_monitor.yml`: Runs every 6 hours (`15 */6 * * *`) and on manual trigger (`workflow_dispatch`).

### Required GitHub Secrets
In your GitHub repository settings, navigate to **Settings > Secrets and variables > Actions** and add:
- `APISH_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `NEON_DATABASE_URL`

Optional retailer secrets:
- `AMAZON_PAAPI_KEY`, `AMAZON_PAAPI_SECRET`, `AMAZON_ASSOCIATE_TAG`
- `FLIPKART_AFFILIATE_ID`, `FLIPKART_AFFILIATE_TOKEN`

---

## Running Automated Tests

Run the full pytest suite:
```powershell
py -m pytest tests/ -v
```
All 19 tests cover configuration, SQLite data integrity, migration verification, collector logic, edition disambiguation, free-to-play protection, watchlist CLI commands, retailer provider statuses, and Telegram notification formatting.
