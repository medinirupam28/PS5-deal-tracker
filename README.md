# PS5 Deal Tracker — India (Digital & Physical Price Tracker)

A personal, production-ready PlayStation 5 deal monitoring system for India (`en-in` region, INR prices). Monitors digital game editions on the official Indian PlayStation Store and tracks physical PS5 game discs across authorized Indian retailers (Amazon India and Flipkart).

---

## Operating Budget & Zero-Cost Architecture

- **Monthly Operating Budget:** ₹0.
- **No Paid APIs or Proxies:** Uses official free tiers exclusively (API.SH free tier, Neon PostgreSQL free tier, GitHub Actions free public/private runner allowance, Telegram Bot API).
- **Laptop-Off Cloud Monitoring:** Fully automated via GitHub Actions scheduled workflows against Neon PostgreSQL in Singapore.
- **Zero Mock Prices / Zero Scraping Violations:** Strictly adheres to authorized APIs and terms of service. Never fabricates prices or bypasses bot defenses/CAPTCHAs.

---

## Key Features

1. **Indian PlayStation Store (`en-in`) Tracking**:
   - Pinned to exact product IDs, edition names, and display INR prices.
   - Preserves user-selected editions (including Deluxe, Ultimate, and Remake collections).
   - Built-in Free-to-Play protection: filters out ₹0 trials/demos/Warzone when paid games are tracked.

2. **Physical PS5 Game Disc Tracking**:
   - Supported retailers: **Amazon India** (`amazon.in`) and **Flipkart** (`flipkart.com`).
   - Platform verification guard: enforces PS5 discs only (rejects PS4-only disc registrations).
   - Independent price history and separate historical-low tracking per retailer listing.
   - Single-URL product registration with automated retailer identification and ASIN/PID extraction.
   - Manual price observation option (`record-price`) when authorized affiliate API keys are pending approval.

3. **Dual-Backend Database Architecture**:
   - **Neon PostgreSQL**: Active cloud database used by GitHub Actions workflows and local scripts.
   - **Local SQLite Fallback**: Automatic local storage (`ps5_deals.db`) with timestamped backups created in `backups/` before any schema changes or migrations.
   - Complete table and history isolation between digital and physical records.

4. **Multi-Tier Deal Detection & Telegram Alerts**:
   - **Multi-Tier Targets**: Monitors three realistic targets per game:
     - `DEAL`: Realistic price worth considering.
     - `GREAT DEAL`: Strong discount worth waiting for.
     - `EXCEPTIONAL`: Rare, unusually low historical price.
   - **Single Strongest Alert Rule**: If a price drops to EXCEPTIONAL, only the strongest tier alert is dispatched (never 3 duplicate alerts).
   - **Escalation & Suppression**: Escalates when price drops into deeper tiers; horizontally suppresses identical prices and de-escalation spam.
   - **Provisional Status Transparency**: Explicitly tags titles with limited observations or unreleased status (e.g. Marvel's Wolverine) with provisional warning badges.
   - Exponential backoff retry logic for temporary network or Telegram dispatch hiccups.

5. **Cloud Automation via GitHub Actions**:
   - Digital monitoring: runs every 6 hours (`cron: '0 */6 * * *'`).
   - Physical monitoring: runs every 6 hours (`cron: '15 */6 * * *'`).
   - Concurrency groups prevent overlapping runs.
   - Automatic failure alerts sent to Telegram if a workflow run encounters an unhandled exception.

---

## Project Structure

```text
PS5DealTracker_completed/
├── .github/workflows/
│   ├── digital_monitor.yml        # Digital monitoring every 6h
│   └── physical_monitor.yml       # Physical monitoring every 6h
├── analyzer/
│   └── deal_detector.py           # Digital & physical deal & low price detector
├── collector/
│   ├── apish_collector.py         # PlayStation Store collector with edition resolver
│   └── retailers/
│       ├── base.py                # BaseRetailerProvider & RetailerPriceResult
│       ├── amazon_in.py           # Amazon India integration (Amazon Creators API)
│       ├── flipkart.py            # Flipkart integration (Flipkart Affiliate API)
│       └── registry.py            # Retailer registry & dispatcher
├── database/
│   ├── db.py                      # Unified DB layer (Neon PostgreSQL + SQLite fallback)
│   └── migrate_to_neon.py         # Atomic SQLite -> Neon migration script with rollback
├── notifications/
│   └── telegram.py                # Formatted Markdown deal notifications with retry logic
├── tests/                         # Full automated pytest test suite (19 tests)
├── .env.example                   # Template for environment variables and secrets
├── .gitignore                     # Excludes credentials, databases, backups, caches
├── config.py                      # Secure configuration loader
├── main.py                        # Digital monitor entry point (`--once` flag supported)
├── manage_watchlist.py            # CLI management tool for digital and physical tracking
├── monitor_physical.py            # Physical monitor entry point
├── requirements.txt               # Lightweight dependencies
└── watchlist.json                 # Master 19-game watchlist definition
```

---

## Master 19-Game Digital Catalog

All 19 games actively monitored with verified store IDs and live INR display prices:

1. **Call of Duty: Modern Warfare 4** (`EP0002-PPSA07950_00-CODMW4STANDARD01`) — ₹5,999
2. **Red Dead Redemption 2: Ultimate Edition** (`EP1004-CUSA08519_00-RDR2ULTMEDTNBUND`) — ₹7,699
3. **Marvel's Spider-Man 2** (`EP9000-PPSA08338_00-MARVELSPIDERMAN2`) — ₹4,999
4. **Ghost of Tsushima DIRECTOR'S CUT** (`EP9000-PPSA03208_00-GHOSTDIRECTORPS5`) — ₹4,999
5. **Grand Theft Auto V (PS4™ & PS5™)** (`EP1004-PPSA01721_00-GTAVCROSSGENBUND`) — ₹3,329
6. **Black Myth: Wukong Digital Deluxe Edition** (`HP6545-PPSA23226_00-GAMEDELUXE000000`) — ₹4,799
7. **Gran Turismo™ 7** (`EP9001-PPSA01316_00-GT7STD0000000PS5`) — ₹4,999
8. **The Last of Us™ Complete** (`EP9000-PPSA29488_00-0000000000000000`) — ₹7,199
9. **Resident Evil Remake Trilogy** (`EP0102-PPSA07412_00-BHB0000000000003`) — ₹4,399
10. **Marvel's Spider-Man: Miles Morales PS4 & PS5** (`EP9000-PPSA01417_00-MARVELSSMMORALES`) — ₹3,999
11. **God of War™** (`EP9000-CUSA07410_00-0000000GODOFWARN`, PS4 on PS5) — ₹749
12. **God of War Ragnarök** (`EP9000-PPSA08330_00-GOWRAGNAROK00000`) — ₹2,499
13. **HITMAN World of Assassination** (`EP3969-PPSA01769_00-0000000000000WOA`) — ₹2,330
14. **007 First Light - Deluxe Edition** (`EP3969-PPSA11386_00-007FLDELUXE00000`) — ₹2,399
15. **Marvel’s Wolverine Digital Deluxe Edition** (`UP9000-PPSA03671_00-WOLVERINEDELUXE0`) — ₹4,311
16. **UNCHARTED: Legacy of Thieves Collection** (`EP9000-PPSA05684_00-UNCHARTED4R00000`) — ₹2,999
17. **F1® 25: 2026 Season Edition** (`UP0006-PPSA24662_00-2026SEASONEDITIO`, alias F1 26) — ₹3,999
18. **Cyberpunk 2077** (`EP4497-PPSA04027_00-00000000000000N1`) — ₹2,999
19. **Minecraft: Ultimate Collection** (`UP4433-PPSA19639_00-MCULTIMATEBUNDLE`) — ₹3,330

---

## Physical Retailer Integration Status

| Retailer | Supported | Status | Integration & Authentication Method |
| :--- | :---: | :---: | :--- |
| **Amazon India** | Yes | `CREDENTIALS_REQUIRED` | **Amazon Creators API** (supersedes PA-API 5.0). Requires `AMAZON_CREATOR_CREDENTIAL_ID` and `AMAZON_CREATOR_CREDENTIAL_SECRET` generated from Amazon Associates Central India (`Tools > Creators API`). Scraping is prohibited. |
| **Flipkart** | Yes | `CREDENTIALS_REQUIRED` | **Flipkart Affiliate API**. Requires `FLIPKART_AFFILIATE_ID` and `FLIPKART_AFFILIATE_TOKEN` via Flipkart Affiliate Dashboard (`API > API Token`). Scraping is prohibited. |
| **Other Retailers** | No | `INACTIVE` | Games The Shop, Games Shop India, and PlayHQ lack sanctioned public APIs and are disabled. |

---

## CLI Usage Guide (`manage_watchlist.py`)

### Digital Game Management
```bash
# List all 19 digital games, live prices, targets, and historical lows
py manage_watchlist.py list

# Set a target price in INR
py manage_watchlist.py target 2 1499

# Pause or resume monitoring for a game
py manage_watchlist.py toggle 5 --disable
py manage_watchlist.py toggle 5 --enable

# Add a new game using a PlayStation Store URL (en-in)
py manage_watchlist.py add "https://store.playstation.com/en-in/product/..."

# Remove a game from active monitoring (preserves price history and alerts)
py manage_watchlist.py remove 19
```

### Physical Disc Management
```bash
# List all registered physical listings
py manage_watchlist.py list-physical

# Inspect retailer integration statuses
py manage_watchlist.py retailers

# Link an Amazon or Flipkart URL to a physical game (PS5 disc only)
py manage_watchlist.py add-listing 1 "https://www.amazon.in/dp/B0CL5KMQ6P" --seller "Appario" --price 3999

# Record a verified manual price observation (marked transparently as MANUAL)
py manage_watchlist.py record-price 1 3999 --seller "Appario"
```

---

## Running the Monitoring Cycles Locally

```bash
# Run one digital monitoring cycle
py main.py --once

# Run one physical disc monitoring cycle
py monitor_physical.py

# Run the complete test suite
py -m pytest tests/ -v
```

---

## Cloud Deployment (GitHub Actions)

The repository runs fully automated in the cloud without requiring your laptop to be powered on.

### Required GitHub Secrets:
Add the following secrets under **Settings > Secrets and variables > Actions**:

1. `APISH_KEY` — API.SH PlayStation Store token.
2. `TELEGRAM_BOT_TOKEN` — Telegram Bot API token.
3. `TELEGRAM_CHAT_ID` — Telegram Chat ID for alerts.
4. `NEON_DATABASE_URL` — Neon PostgreSQL connection URL.
5. *(Optional)* `AMAZON_CREATOR_CREDENTIAL_ID` & `AMAZON_CREATOR_CREDENTIAL_SECRET` — If approved for Amazon Creators API.
6. *(Optional)* `FLIPKART_AFFILIATE_ID` & `FLIPKART_AFFILIATE_TOKEN` — If approved for Flipkart Affiliate API.
