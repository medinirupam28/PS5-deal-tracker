import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from manage_watchlist import cmd_list, cmd_target, cmd_toggle, cmd_remove, cmd_export, cmd_import, cmd_add
from database.db import Database

class DummyArgs:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def test_list_command(capsys):
    args = DummyArgs()
    ret = cmd_list(args)
    assert ret == 0
    captured = capsys.readouterr()
    assert "Call of Duty Modern Warfare 4" in captured.out
    assert "Red Dead Redemption 2" in captured.out

def test_target_command(capsys):
    # Set target price for game 2 (Red Dead Redemption 2)
    args = DummyArgs(id=2, price="1499")
    ret = cmd_target(args)
    assert ret == 0
    db = Database()
    assert db.get_target_price(2) == 1499.0

def test_toggle_and_remove_preserves_history():
    db = Database()
    # Check initial history count for game 2
    initial_history = len(db._fetchall("SELECT id FROM price_history WHERE game_id = 2"))
    assert initial_history > 0

    # Pause monitoring
    cmd_toggle(DummyArgs(id=2, enable=False, disable=True))
    game = db.get_game_by_id(2)
    assert game["is_active"] is False

    # Resume monitoring
    cmd_toggle(DummyArgs(id=2, enable=True, disable=False))
    game = db.get_game_by_id(2)
    assert game["is_active"] is True

    # Remove (soft removal)
    cmd_remove(DummyArgs(id=2, yes=True))
    game = db.get_game_by_id(2)
    assert game["is_active"] is False

    # Verify history is completely intact!
    after_history = len(db._fetchall("SELECT id FROM price_history WHERE game_id = 2"))
    assert after_history == initial_history

    # Reactivate game 2 for later stages
    cmd_toggle(DummyArgs(id=2, enable=True, disable=False))
    assert db.get_game_by_id(2)["is_active"] is True

def test_export_import(tmp_path):
    export_file = tmp_path / "export_test.json"
    cmd_export(DummyArgs(output=str(export_file)))
    assert export_file.exists()

    with export_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["exported_count"] >= 9
    assert len(data["games"]) >= 9

    # Re-importing should reconnect without creating duplicate games
    cmd_import(DummyArgs(file=str(export_file)))
    db = Database()
    games = db.get_all_digital_games()
    assert len(games) == data["exported_count"]

@patch("manage_watchlist.APISHCollector")
def test_cmd_add_duplicate_protection(mock_collector_class):
    mock_collector = MagicMock()
    mock_collector.get_available_editions.return_value = [
        {
            "game_name": "Marvel's Spider-Man 2",
            "edition_id": "10002456",
            "edition_name": "Standard Edition",
            "current_price": 2499.0,
            "original_price": 4999.0,
            "discount_text": "50% off",
            "sale_ends": None,
            "store_url": "https://store.playstation.com/en-in/concept/10002456",
            "is_free": False,
            "is_ps5": True,
            "currency": "INR",
        }
    ]
    mock_collector_class.return_value = mock_collector

    # Add game that already exists in DB (ID 3, store_id 10002456)
    args = DummyArgs(
        url="https://store.playstation.com/en-in/concept/10002456",
        edition=None,
        edition_id=None,
        target=2199.0,
        allow_free=False,
        yes=True
    )
    ret = cmd_add(args)
    assert ret == 0

    db = Database()
    # Check that game 3 target price was updated and no duplicate was added
    game = db.get_game_by_store_id("10002456")
    assert game is not None
    assert game["id"] == 3
    assert db.get_target_price(3) == 2199.0
