"""Unit tests for Multi-Tier Target Prices and Deal Alert Deduplication.

Tests all three tiers (DEAL, GREAT DEAL, EXCEPTIONAL), escalation,
duplicate suppression, provisional flags, and Telegram message dispatching
using an isolated temporary SQLite database.
"""

import tempfile
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

    # Seed test game
    gid = test_db.add_game(
        name="Marvel's Spider-Man 2",
        store_id="EP9000-PPSA08338_00-MARVELSPIDERMAN2",
        store_url="https://store.playstation.com/en-in/product/EP9000-PPSA08338_00-MARVELSPIDERMAN2",
        platform="PS5",
        edition_name="Standard Edition"
    )

    # Set multi-tier targets: Deal=3499, Great=2849, Exceptional=2199
    test_db.set_target_tiers(
        game_id=gid,
        target_deal=3499.0,
        target_great_deal=2849.0,
        target_exceptional=2199.0,
        is_provisional=False,
        target_notes="Sony first-party discount cycle"
    )

    # Seed initial baseline price (list price: 4999)
    test_db.save_price(gid, 4999.0, currency="INR", original_price=4999.0)

    yield test_db, gid

    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass


def test_multi_tier_targets_stored_and_retrieved(isolated_db):
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)
    assert tiers is not None
    assert tiers["target_deal"] == 3499.0
    assert tiers["target_great_deal"] == 2849.0
    assert tiers["target_exceptional"] == 2199.0
    assert tiers["is_provisional"] is False
    assert tiers["target_notes"] == "Sony first-party discount cycle"

    # Verify get_active_digital_games returns all multi-tier columns
    active = test_db.get_active_digital_games()
    assert len(active) == 1
    assert active[0]["target_deal"] == 3499.0
    assert active[0]["target_great_deal"] == 2849.0
    assert active[0]["target_exceptional"] == 2199.0


def test_deal_tier_triggering_and_deduplication(isolated_db):
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Price hits DEAL tier (₹3,499)
    detection = detect_deal(
        game_id=gid,
        current_price=3499.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    assert "DEAL" in detection["alert_types"]
    assert "GREAT DEAL" not in detection["alert_types"]
    assert "EXCEPTIONAL DEAL" not in detection["alert_types"]
    assert detection["tier"] == "DEAL"

    # Simulate recording the alert in database
    for reason in detection["alert_types"]:
        test_db.record_alert(gid, 3499.0, reason)

    # Next check at same price (₹3,499) -> must be duplicate suppressed
    dup_detection = detect_deal(
        game_id=gid,
        current_price=3499.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert dup_detection is None


def test_escalation_from_deal_to_great_to_exceptional(isolated_db):
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # 1. Trigger DEAL at ₹3,499
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
    assert det2 is not None
    assert "GREAT DEAL" in det2["alert_types"]
    assert det2["tier"] == "GREAT DEAL"
    for a in det2["alert_types"]:
        test_db.record_alert(gid, 2849.0, a)

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
    assert det3 is not None
    assert "EXCEPTIONAL DEAL" in det3["alert_types"]
    assert det3["tier"] == "EXCEPTIONAL DEAL"
    for a in det3["alert_types"]:
        test_db.record_alert(gid, 2199.0, a)

    # 4. Subsequent check at same price (₹2,199) -> suppressed
    det4 = detect_deal(
        game_id=gid,
        current_price=2199.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det4 is None

    # 5. De-escalation (price rises back to ₹2,849) -> suppressed!
    det5 = detect_deal(
        game_id=gid,
        current_price=2849.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert det5 is None


def test_immediate_exceptional_sends_single_strongest_alert(isolated_db):
    """Ensure a price reaching EXCEPTIONAL sends only the strongest tier alert,

    not 3 separate notifications for DEAL, GREAT DEAL, and EXCEPTIONAL.
    """
    test_db, gid = isolated_db
    tiers = test_db.get_target_tiers(gid)

    # Price drops directly to ₹1,999 (below exceptional ₹2,199)
    detection = detect_deal(
        game_id=gid,
        current_price=1999.0,
        original_price=4999.0,
        target_deal=tiers["target_deal"],
        target_great_deal=tiers["target_great_deal"],
        target_exceptional=tiers["target_exceptional"],
        db_instance=test_db,
    )
    assert detection is not None
    # Must only contain EXCEPTIONAL DEAL as target alert
    target_alerts = [a for a in detection["alert_types"] if "DEAL" in a]
    assert target_alerts == ["EXCEPTIONAL DEAL"]
    assert "GREAT DEAL" not in detection["alert_types"]
    assert "DEAL" not in detection["alert_types"]
    assert detection["tier"] == "EXCEPTIONAL DEAL"


def test_provisional_flag_and_notes(isolated_db):
    test_db, gid = isolated_db
    # Update to provisional (like Wolverine)
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
