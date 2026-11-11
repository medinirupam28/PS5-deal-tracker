import sqlite3
import pytest
from pathlib import Path

from database.migrate_to_neon import create_sqlite_backup, get_sqlite_counts, SQLITE_DB_PATH

def test_sqlite_counts():
    counts = get_sqlite_counts(SQLITE_DB_PATH)
    assert counts.get("games") >= 9
    assert counts.get("price_history") >= 9
    assert counts.get("watchlist") >= 9
    assert counts.get("alerts") >= 4
    assert counts.get("retailers") == 5

def test_backup_creation():
    backup_path = create_sqlite_backup()
    assert backup_path.exists()
    assert backup_path.stat().st_size > 0
    # Verify backup database integrity
    conn = sqlite3.connect(backup_path)
    cur = conn.cursor()
    games_count = cur.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert games_count >= 9
    conn.close()
