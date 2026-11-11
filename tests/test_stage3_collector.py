import pytest
from unittest.mock import MagicMock, patch

from collector.apish_collector import (
    APISHCollector,
    extract_store_id,
    parse_store_price,
    validate_store_url,
)

def test_parse_store_price():
    assert parse_store_price("Rs 5,999") == 5999.0
    assert parse_store_price("₹4,999.00") == 4999.0
    assert parse_store_price("Free") == 0.0
    assert parse_store_price("FREE") == 0.0
    assert parse_store_price(None) is None
    assert parse_store_price("Invalid") is None

def test_validate_store_url():
    assert validate_store_url("https://store.playstation.com/en-in/concept/10001130") is True
    assert validate_store_url("https://store.playstation.com/en-in/product/EP9000-PPSA03208_00-GHOSTDIRECTORPS5") is True
    # Rejects non-Indian region
    assert validate_store_url("https://store.playstation.com/en-us/concept/10001130") is False
    assert validate_store_url("https://store.playstation.com/en-gb/product/12345") is False
    assert validate_store_url("https://randomsite.com/game") is False

def test_extract_store_id():
    assert extract_store_id("https://store.playstation.com/en-in/concept/10001130") == "10001130"
    assert extract_store_id("https://store.playstation.com/en-in/product/EP9000-PPSA03208_00-GHOSTDIRECTORPS5") == "EP9000-PPSA03208_00-GHOSTDIRECTORPS5"

@patch("collector.apish_collector.requests.Session.get")
def test_free_to_play_protection(mock_get):
    """Verify that a paid game never defaults to a 0.0 Free-to-Play/Warzone edition."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "Call of Duty Modern Warfare",
        "region": "en-in",
        "editions": [
            {
                "id": "WARZONE_FREE",
                "name": "Call of Duty Warzone (Free to Play)",
                "prices": [{"currency": "INR", "price_text": "Free", "original_price_text": "Free"}]
            },
            {
                "id": "MW_CROSS_GEN",
                "name": "Call of Duty Modern Warfare Cross-Gen Bundle",
                "prices": [{"currency": "INR", "price_text": "₹4,999", "original_price_text": "₹4,999"}]
            },
            {
                "id": "MW_VAULT",
                "name": "Call of Duty Modern Warfare Vault Edition",
                "prices": [{"currency": "INR", "price_text": "₹6,499", "original_price_text": "₹6,499"}]
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    collector = APISHCollector(region="en-in")
    game_entry = {
        "name": "Call of Duty Modern Warfare",
        "store_url": "https://store.playstation.com/en-in/concept/10001130",
        "store_id": "10001130"
    }

    # By default, allow_free=False must select the paid Cross-Gen Bundle (₹4,999), NOT the ₹0 free Warzone!
    selected = collector.get_game_price(game_entry, allow_free=False)
    assert selected["current_price"] == 4999.0
    assert "Warzone" not in selected["edition_name"]
    assert selected["edition_name"] == "Call of Duty Modern Warfare Cross-Gen Bundle"

    # If user explicitly allowed free, then free is allowed
    selected_free = collector.get_game_price(game_entry, allow_free=True)
    assert selected_free["current_price"] == 0.0

@patch("collector.apish_collector.requests.Session.get")
def test_region_mismatch_rejected(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "Test Game",
        "region": "en-us",
        "editions": []
    }
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    collector = APISHCollector(region="en-in")
    with pytest.raises(ValueError, match="Region mismatch"):
        collector.lookup_game("https://store.playstation.com/en-in/concept/10001130")
