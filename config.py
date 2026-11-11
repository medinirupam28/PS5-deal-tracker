"""Configuration management for PS5 Deal Tracker.

Loads configuration from environment variables or .env file.
Ensures secrets are never exposed or printed.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

# Load .env file if present
load_dotenv(BASE_DIR / ".env")

# API Keys & Credentials
APISH_KEY = os.getenv("APISH_KEY", "").strip()

# Telegram Credentials
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Backwards compatibility aliases
BOT_TOKEN = TELEGRAM_BOT_TOKEN
CHAT_ID = TELEGRAM_CHAT_ID

# Neon PostgreSQL Database URL
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL", "").strip()

# Retailer Credentials (Optional)
# Amazon Creators API (replaces legacy PA-API 5.0)
AMAZON_CREATOR_CREDENTIAL_ID = os.getenv("AMAZON_CREATOR_CREDENTIAL_ID", "").strip()
AMAZON_CREATOR_CREDENTIAL_SECRET = os.getenv("AMAZON_CREATOR_CREDENTIAL_SECRET", "").strip()
AMAZON_CREATOR_VERSION = os.getenv("AMAZON_CREATOR_VERSION", "v1").strip()
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "").strip()

# Legacy aliases if set
AMAZON_PAAPI_KEY = os.getenv("AMAZON_PAAPI_KEY", "").strip()
AMAZON_PAAPI_SECRET = os.getenv("AMAZON_PAAPI_SECRET", "").strip()

# Flipkart Affiliate API
FLIPKART_AFFILIATE_ID = os.getenv("FLIPKART_AFFILIATE_ID", "").strip()
FLIPKART_AFFILIATE_TOKEN = os.getenv("FLIPKART_AFFILIATE_TOKEN", "").strip()

# Default Settings
DEFAULT_REGION = "en-in"
DEFAULT_CURRENCY = "INR"
DEFAULT_MINIMUM_DISCOUNT = 30.0
DEFAULT_CHECK_INTERVAL_HOURS = 6


def is_neon_configured() -> bool:
    """Return True if a Neon/PostgreSQL database URL is configured."""
    return bool(NEON_DATABASE_URL and NEON_DATABASE_URL.startswith(("postgres://", "postgresql://")))


def is_telegram_configured() -> bool:
    """Return True if Telegram bot token and chat ID are present."""
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def is_apish_configured() -> bool:
    """Return True if API.SH key is present."""
    return bool(APISH_KEY)
