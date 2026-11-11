import pytest
from unittest.mock import MagicMock, patch

from collector.retailers.registry import retailer_registry
from collector.retailers.base import RetailerStatus
from analyzer.deal_detector import detect_physical_deal
from notifications.telegram import send_deal_alert, send_physical_deal_alert
from database.db import Database
from manage_watchlist import cmd_retailers, cmd_add_physical, cmd_add_listing, cmd_list_physical

class DummyArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def test_retailer_providers_status_matrix():
    """Verify that all 5 Indian retailers report compliant statuses and never emit mock prices."""
    providers = retailer_registry.get_all_providers()
    assert len(providers) == 5

    amazon = retailer_registry.get_provider("amazon_in")
    assert amazon.code == "amazon_in"
    # When PAAPI credentials are absent in test environment
    assert amazon.get_status() == RetailerStatus.CREDENTIALS_REQUIRED
    res = amazon.fetch_price("https://www.amazon.in/dp/B08L5WHJLS")
    assert res.success is False
    assert res.price is None
    assert "PA-API" in res.error_message

    flipkart = retailer_registry.get_provider("flipkart")
    assert flipkart.code == "flipkart"
    assert flipkart.get_status() == RetailerStatus.CREDENTIALS_REQUIRED
    res = flipkart.fetch_price("https://www.flipkart.com/p/item")
    assert res.success is False
    assert res.price is None

    gts = retailer_registry.get_provider("games_the_shop")
    assert gts.get_status() == RetailerStatus.UNAVAILABLE
    res = gts.fetch_price("https://www.gamestheshop.com/product")
    assert res.success is False
    assert res.price is None

    gs = retailer_registry.get_provider("games_shop_in")
    assert gs.get_status() == RetailerStatus.UNAVAILABLE

    playhq = retailer_registry.get_provider("playhq")
    assert playhq.get_status() == RetailerStatus.UNAVAILABLE

def test_physical_deal_detection(tmp_path):
    db = Database(sqlite_path=tmp_path / "test_phys.db")
    db.initialize_database()

    pid = db.add_physical_game("Spider-Man 2 Physical", target_price=3000.0)
    lid = db.add_physical_listing(pid, "amazon_in", "https://www.amazon.in/dp/B08L5WHJLS")

    # Baseline observation: 3999 -> no deal
    db.save_physical_price(lid, 3999.0, original_price=4999.0, discount_percentage=20.0)

    # Second observation: price drops to 2800 (below target 3000 and new historical low)
    deal = detect_physical_deal(
        physical_game_id=pid,
        listing_id=lid,
        current_price=2800.0,
        original_price=4999.0,
        target_price=3000.0,
        minimum_discount=20.0,
        db_instance=db
    )
    assert deal is not None
    assert "TARGET PRICE REACHED" in deal["alert_types"]
    assert "NEW HISTORICAL LOW" in deal["alert_types"]
    assert deal["current_price"] == 2800.0

@patch("notifications.telegram.requests.post")
def test_telegram_notifications(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True}
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    # Test digital alert formatting
    game = {"name": "Ghost of Tsushima Director's Cut", "store_url": "https://store.playstation.com/en-in/product/123", "target_price": 2500.0}
    price_data = {"edition_name": "Director's Cut", "original_price": 4999.0, "store_url": "https://store.playstation.com/en-in/product/123"}
    detection = {
        "current_price": 2499.0,
        "savings": 2500.0,
        "discount_percentage": 50.0,
        "previous_historical_low": 4999.0,
        "alert_types": ["TARGET PRICE REACHED", "NEW HISTORICAL LOW"]
    }
    sent = send_deal_alert(game, price_data, detection)
    assert sent is True
    assert mock_post.called
    sent_payload = mock_post.call_args[1]["json"]
    assert "Ghost of Tsushima" in sent_payload["text"]
    assert "₹2,499" in sent_payload["text"]
    assert "TARGET PRICE REACHED" in sent_payload["text"]

    # Test physical alert formatting
    phys_item = {
        "title": "God of War Ragnarok Disc",
        "retailer_name": "Amazon India",
        "product_url": "https://www.amazon.in/dp/B0B5Z8Z4WZ",
        "seller_name": "Appario Retail",
        "target_price": 2999.0,
    }
    phys_price_data = {"original_price": 4999.0}
    phys_detection = {
        "current_price": 2899.0,
        "discount_percentage": 42.0,
        "previous_historical_low": 3499.0,
        "alert_types": ["TARGET PRICE REACHED", "NEW HISTORICAL LOW"]
    }
    sent_phys = send_physical_deal_alert(phys_item, phys_price_data, phys_detection)
    assert sent_phys is True
    phys_payload = mock_post.call_args[1]["json"]
    assert "God of War Ragnarok Disc" in phys_payload["text"]
    assert "Amazon India" in phys_payload["text"]
    assert "Appario Retail" in phys_payload["text"]
    assert "₹2,899" in phys_payload["text"]

def test_physical_cli_commands(capsys):
    ret = cmd_retailers(DummyArgs())
    assert ret == 0
    captured = capsys.readouterr()
    assert "Amazon India" in captured.out
    assert "Flipkart" in captured.out
    assert "Games The Shop" in captured.out
