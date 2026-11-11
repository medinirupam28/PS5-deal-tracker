import os
import sqlite3
import pytest
from pathlib import Path

import config
from database.db import Database

def test_config_defaults():
    assert config.DEFAULT_REGION == "en-in"
    assert config.DEFAULT_CURRENCY == "INR"
    assert config.DEFAULT_MINIMUM_DISCOUNT == 30.0
    assert config.DEFAULT_CHECK_INTERVAL_HOURS == 2
    # Ensure aliases work
    assert config.BOT_TOKEN == config.TELEGRAM_BOT_TOKEN
    assert config.CHAT_ID == config.TELEGRAM_CHAT_ID

def test_database_sqlite_preserved_data():
    db = Database(force_sqlite=True)
    # Call initialize_database to ensure any new columns/tables exist
    db.initialize_database()

    # Verify existing 9 games and expanded 19 games
    games = db._fetchall("SELECT id, name, store_id FROM games ORDER BY id ASC")
    assert len(games) >= 9, f"Expected at least 9 games, got {len(games)}"

    # Check COD Modern Warfare (verified ID 1 preserved)
    assert games[0][0] == 1
    assert "Call of Duty" in games[0][1]
    assert games[0][2] in ("10001130", "EP0002-PPSA07950_00-CODMW4STANDARD01")

    # Verify existing price history
    history = db._fetchall("SELECT id, game_id, price FROM price_history ORDER BY id ASC")
    assert len(history) >= 9

    # Verify existing alerts
    alerts = db._fetchall("SELECT id, game_id, alert_type FROM alerts ORDER BY id ASC")
    assert len(alerts) >= 4

    # Verify default retailers are seeded
    retailers = db._fetchall("SELECT code, check_interval_hours FROM retailers ORDER BY code ASC")
    codes = {r[0] for r in retailers}
    assert "amazon_in" in codes
    assert "flipkart" in codes
    assert "games_the_shop" in codes
    assert "games_shop_in" in codes
    assert "playhq" in codes

def test_isolated_temp_sqlite(tmp_path):
    temp_db_path = tmp_path / "temp_test.db"
    temp_db = Database(sqlite_path=temp_db_path)
    temp_db.initialize_database()

    # Add digital game
    gid = temp_db.add_game("Test Game", "TEST-123", "https://store.playstation.com/en-in/concept/123", edition_name="Standard")
    assert gid > 0
    temp_db.set_target_price(gid, 2499.0)
    assert temp_db.get_target_price(gid) == 2499.0

    temp_db.save_price(gid, 2999.0)
    assert temp_db.get_historical_low(gid) == 2999.0

    # Add physical game
    pid = temp_db.add_physical_game("Physical Test Game", target_price=3000.0)
    assert pid > 0
    lid = temp_db.add_physical_listing(pid, "amazon_in", "https://amazon.in/dp/TEST123")
    assert lid > 0

    temp_db.save_physical_price(lid, 2800.0, original_price=3999.0, discount_percentage=30.0)
    assert temp_db.get_physical_historical_low(pid) == 2800.0

    # Verify digital historical low is untouched and physical historical low is untouched
    assert temp_db.get_historical_low(gid) == 2999.0
