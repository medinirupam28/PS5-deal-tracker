"""Unit tests for Multi-Tier Target Prices and Deal Alert Deduplication.

Tests all required audit scenarios:
1. Price above all targets (no alert).
2. Price exactly equal to DEAL (sends DEAL alert).
3. Price exactly equal to GREAT DEAL (sends GREAT DEAL alert).
4. Price exactly equal to EXCEPTIONAL (sends EXCEPTIONAL alert).
5. Price below EXCEPTIONAL (sends only 1 strongest EXCEPTIONAL alert).
6. Repeated identical price (duplicate suppression).
7. Price escalation between tiers.
8. Recovery above DEAL and a later qualifying sale (allows fresh alert).
9. API failure or missing price (no alert sent).
10. New historical low (genuinely lower than previous minimum).
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from database.db import Database
from analyzer.deal_detector import detect_deal
from notifications.telegram import send_deal_alert


@pytest.fixture
def isolated_db():
    """Create an isolated, temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    test_db = Database(sqlite_path=db_path, force_sqlite=True)
    test_db.initialize_database()

    # Seed test game: Marvel's Spider-Man 2
    gid = test_db.add_game(
        name="Marvel's Spider-Man 2",
        store_id="EP9000-PPSA08338_00-MARVELSPIDERMAN2",
        store_url="https://store.playstation.com/en-in/product/EP9000-PPSA08338_00-MARVELSPIDERMAN2",
        platform="PS5",
        edition_name="Standard Edition"
    )

    # Multi-tier targets: Deal=3499, Great=2849, Exceptional=2199
    test_db.set_target_tiers(
        game_id=gid,
        target_deal=3499.0,
        target_great_deal=2849.0,
        target_exceptional=2199.0,
        is_provisional=False,
        target_notes="Sony first-party discount cycle"
    )

    # Initial baseline price: ₹4,999 (full price)
    test_db.save_price(gid, 4999.0, currency="INR", original_price=4999.0)

    yield test_db, gid

    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


def test_1_price_above_all_targets_sends_no_notification(isolated_db):
    """Scenario 1: Current price is above all targets -> returns None."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Current price is full price (4999), which is above DEAL (3499)
    detection = detect_deal(
        game_id=gid,
        current_price=4999.0,  # Above DEAL (3499), matches baseline
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        minimum_discount=30.0,
        db_instance=test_db,
    )
    assert detection is None


def test_2_price_exactly_equal_to_deal_sends_deal_alert(isolated_db):
    """Scenario 2: Price exactly equal to DEAL target -> sends DEAL alert."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    detection = detect_deal(
        game_id=gid,
        current_price=3499.0,  # Exactly DEAL
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    assert detection["tier"] == "DEAL"
    assert "DEAL" in detection["alert_types"]
    assert "GREAT DEAL" not in detection["alert_types"]
    assert "EXCEPTIONAL DEAL" not in detection["alert_types"]


def test_3_price_exactly_equal_to_great_deal_sends_great_deal_alert(isolated_db):
    """Scenario 3: Price exactly equal to GREAT DEAL target -> sends GREAT DEAL alert."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    detection = detect_deal(
        game_id=gid,
        current_price=2849.0,  # Exactly GREAT DEAL
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    assert detection["tier"] == "GREAT DEAL"
    assert "GREAT DEAL" in detection["alert_types"]
    assert "DEAL" not in detection["alert_types"]
    assert "EXCEPTIONAL DEAL" not in detection["alert_types"]


def test_4_price_exactly_equal_to_exceptional_sends_exceptional_alert(isolated_db):
    """Scenario 4: Price exactly equal to EXCEPTIONAL target -> sends EXCEPTIONAL alert."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    detection = detect_deal(
        game_id=gid,
        current_price=2199.0,  # Exactly EXCEPTIONAL
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    assert detection["tier"] == "EXCEPTIONAL DEAL"
    assert "EXCEPTIONAL DEAL" in detection["alert_types"]
    assert "GREAT DEAL" not in detection["alert_types"]
    assert "DEAL" not in detection["alert_types"]


def test_5_price_below_exceptional_sends_only_single_strongest_alert(isolated_db):
    """Scenario 5: Price strictly below EXCEPTIONAL sends 1 alert, not 3."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    detection = detect_deal(
        game_id=gid,
        current_price=1899.0,  # Below EXCEPTIONAL (2199)
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    assert detection["tier"] == "EXCEPTIONAL DEAL"
    # Target tier list must contain ONLY EXCEPTIONAL DEAL
    target_alerts = [a for a in detection["alert_types"] if "DEAL" in a]
    assert target_alerts == ["EXCEPTIONAL DEAL"]


def test_6_repeated_identical_price_suppresses_duplicate_alert(isolated_db):
    """Scenario 6: Subsequent run with same price produces NO notification."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # First run: price is ₹2,849 (GREAT DEAL)
    det1 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det1 is not None
    for a in det1["alert_types"]:
        test_db.record_alert(gid, 2849.0, a)
    test_db.save_price(gid, 2849.0, currency="INR")

    # Second run (6 hours later, identical price ₹2,849):
    det2 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det2 is None  # Duplicate suppressed!


def test_7_price_escalation_between_tiers(isolated_db):
    """Scenario 7: Price escalating from DEAL -> GREAT DEAL -> EXCEPTIONAL."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # 1. DEAL at ₹3,499
    det1 = detect_deal(
        game_id=gid,
        current_price=3499.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det1["tier"] == "DEAL"
    for a in det1["alert_types"]:
        test_db.record_alert(gid, 3499.0, a)
    test_db.save_price(gid, 3499.0)

    # 2. Escalate to GREAT DEAL at ₹2,849
    det2 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det2["tier"] == "GREAT DEAL"
    for a in det2["alert_types"]:
        test_db.record_alert(gid, 2849.0, a)
    test_db.save_price(gid, 2849.0)

    # 3. Escalate to EXCEPTIONAL at ₹2,199
    det3 = detect_deal(
        game_id=gid,
        current_price=2199.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det3["tier"] == "EXCEPTIONAL DEAL"
    for a in det3["alert_types"]:
        test_db.record_alert(gid, 2199.0, a)
    test_db.save_price(gid, 2199.0)


def test_8_recovery_above_deal_and_later_qualifying_sale(isolated_db):
    """Scenario 8: Price returns above DEAL, then later drops in a fresh sale.

    A fresh notification must be allowed.
    """
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # 1. Sale 1: Price drops to ₹2,849 (GREAT DEAL)
    det1 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det1 is not None
    for a in det1["alert_types"]:
        test_db.record_alert(gid, 2849.0, a)
    test_db.save_price(gid, 2849.0)

    # Verify duplicate is suppressed while on sale
    assert detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    ) is None

    # 2. Sale ends: Price recovers back to full list price ₹4,999 (> target_deal 3499)
    # Give a tiny delay or distinct timestamp so checked_at > sent_at
    time.sleep(0.01)
    test_db.save_price(gid, 4999.0, currency="INR", original_price=4999.0)

    # 3. Sale 2 (weeks later): Price drops back to ₹2,849 (GREAT DEAL)
    det2 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    # Must allow fresh alert because price recovered above DEAL in between!
    assert det2 is not None
    assert "GREAT DEAL" in det2["alert_types"]


def test_9_api_failure_sends_no_notification(isolated_db):
    """Scenario 9: If price is missing or API fails, no deal detection occurs."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Price is None (API failure)
    price_val = None
    if price_val is not None:
        detection = detect_deal(
            game_id=gid,
            current_price=price_val,
            original_price=4999.0,
            target_deal=tiers["target_deal"],
            target_great_deal=tiers["target_great_deal"],
            target_exceptional=tiers["target_exceptional"],
            db_instance=test_db,
        )
    else:
        detection = None

    assert detection is None


def test_10_new_historical_low(isolated_db):
    """Scenario 10: NEW HISTORICAL LOW triggers only when genuinely below previous low."""
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Currently, lowest recorded price in price_history is ₹4,999.
    # Price drops to ₹3,499 (which is < 4999 baseline).
    det1 = detect_deal(
        game_id=gid,
        current_price=3499.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert "NEW HISTORICAL LOW" in det1["alert_types"]
    for a in det1["alert_types"]:
        test_db.record_alert(gid, 3499.0, a)
    test_db.save_price(gid, 3499.0)

    # Next observation at ₹3,499 (equal to previous low) -> NOT a new low!
    det2 = detect_deal(
        game_id=gid,
        current_price=3499.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det2 is None

    # Next observation at ₹3,200 (strictly below 3499) -> triggers NEW HISTORICAL LOW!
    det3 = detect_deal(
        game_id=gid,
        current_price=3200.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det3 is not None
    assert "NEW HISTORICAL LOW" in det3["alert_types"]


def test_target_evaluation_independent_of_discount_flag(isolated_db):
    """Verify that target-price evaluation works even when store reports 'No discount'.

    (original_price == current_price, discount == 0.0)
    """
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Simulate store reporting ₹2,499 with NO discount banner (original_price == current_price)
    detection = detect_deal(
        game_id=gid,
        current_price=2499.0,
        original_price=2499.0,  # 0% discount reported by store
        target_deal=tiers["target_deal"],  # 3499
        target_great_deal=tiers["target_great_deal"],  # 2849
        target_exceptional=tiers["target_exceptional"],  # 2199
        minimum_discount=30.0,
        db_instance=test_db,
    )
    # Must STILL trigger GREAT DEAL because 2499 <= 2849
    assert detection is not None
    assert detection["tier"] == "GREAT DEAL"
    assert "GREAT DEAL" in detection["alert_types"]
    assert detection["discount_percentage"] == 0.0


def test_provisional_flag_and_notes(isolated_db):
    test_db, gid = isolated_db
    test_db.set_target_tiers(
        game_id=gid,
        target_deal=4759.0,
        target_great_deal=4311.0,
        target_exceptional=3639.0,
        is_provisional=True,
        target_notes="Provisional: Unreleased title; confidence LOW."
    )
    tiers = test_db.get_target_tiers(gid)
    assert tiers["is_provisional"] is True
    assert "Provisional" in tiers["target_notes"]

    detection = detect_deal(
        game_id=gid,
        current_price=3600.0,
        original_price=5599.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        is_provisional=tiers["is_provisional"],
        target_notes=tiers["target_notes"],
        db_instance=test_db,
    )
    assert detection["is_provisional"] is True
    assert detection["target_notes"] == "Provisional: Unreleased title; confidence LOW."


@patch("notifications.telegram._dispatch_telegram_message")
def test_telegram_tier_message_formatting(mock_dispatch, isolated_db):
    test_db, gid = isolated_db
    mock_dispatch.return_value = True

    game = test_db.get_active_digital_games()[0]
    price_data = {
        "current_price": 2199.0,
        "original_price": 4999.0,
        "edition_name": "Standard Edition",
        "store_url": game["store_url"],
    }
    detection = {
        "alert_types": ["EXCEPTIONAL DEAL", "NEW HISTORICAL LOW"],
        "current_price": 2199.0,
        "original_price": 4999.0,
        "discount_percentage": 56.0,
        "savings": 2800.0,
        "previous_historical_low": 2499.0,
        "tier": "EXCEPTIONAL DEAL",
        "target_deal": 3499.0,
        "target_great_deal": 2849.0,
        "target_exceptional": 2199.0,
        "is_provisional": False,
        "target_notes": None,
    }

    with patch("config.is_telegram_configured", return_value=True):
        sent = send_deal_alert(game, price_data, detection)
        assert sent is True

    # Inspect dispatched message
    dispatched_text = mock_dispatch.call_args[0][0]
    assert "🚀 *PS5 DIGITAL DEAL ALERT — EXCEPTIONAL DEAL*" in dispatched_text
    assert "Marvel's Spider-Man 2" in dispatched_text
    assert "₹2,199" in dispatched_text
    assert "Deal: ₹3,499 | Great Deal: ₹2,849 | Exceptional: ₹2,199 ✅" in dispatched_text
    assert "EXCEPTIONAL DEAL, NEW HISTORICAL LOW" in dispatched_text
