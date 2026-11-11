"""Unified Database Access Layer for PS5 Deal Tracker.

Supports both PostgreSQL (Neon) and SQLite (Local Backup/Fallback).
Maintains identical signatures, strict table isolation between digital and physical,
and guarantees historical data preservation.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config

DB_PATH = Path(__file__).resolve().parents[1] / "ps5_deals.db"

# Try importing psycopg for PostgreSQL support
try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False


def is_postgres_active() -> bool:
    """Check if PostgreSQL (Neon) is configured and driver is available."""
    return bool(config.is_neon_configured() and PSYCOPG_AVAILABLE)


class Database:
    def __init__(self, db_url: Optional[str] = None, sqlite_path: Optional[Path] = None, force_sqlite: bool = False):
        if force_sqlite or sqlite_path is not None:
            self.db_url = None
            self.use_postgres = False
        else:
            self.db_url = db_url if db_url is not None else config.NEON_DATABASE_URL
            self.use_postgres = bool(self.db_url and self.db_url.startswith(("postgres://", "postgresql://")) and PSYCOPG_AVAILABLE)

        self.sqlite_path = sqlite_path if sqlite_path is not None else DB_PATH

    @contextmanager
    def get_connection(self):
        if self.use_postgres:
            conn = psycopg.connect(self.db_url)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _execute(self, query: str, params: Tuple[Any, ...] = ()) -> Any:
        """Execute a query adapting parameter syntax (? for sqlite, %s for postgres)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            adapted_query = query
            if self.use_postgres:
                adapted_query = query.replace("?", "%s")
            cursor.execute(adapted_query, params)
            return cursor

    def _fetchone(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[Tuple]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            adapted_query = query
            if self.use_postgres:
                adapted_query = query.replace("?", "%s")
            cursor.execute(adapted_query, params)
            return cursor.fetchone()

    def _fetchall(self, query: str, params: Tuple[Any, ...] = ()) -> List[Tuple]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            adapted_query = query
            if self.use_postgres:
                adapted_query = query.replace("?", "%s")
            cursor.execute(adapted_query, params)
            return cursor.fetchall()

    def initialize_database(self):
        """Create tables for both digital and physical trackers, and apply safe migrations."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self.use_postgres:
                # PostgreSQL schema
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    store_id TEXT NOT NULL UNIQUE,
                    platform TEXT NOT NULL DEFAULT 'PS5',
                    store_url TEXT NOT NULL,
                    edition_name TEXT DEFAULT 'Standard Edition',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    original_price REAL,
                    discount_percentage REAL DEFAULT 0.0,
                    checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_history_game_date ON price_history(game_id, checked_at);

                CREATE TABLE IF NOT EXISTS watchlist (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,
                    target_price REAL,
                    target_deal REAL,
                    target_great_deal REAL,
                    target_exceptional REAL,
                    is_provisional BOOLEAN NOT NULL DEFAULT FALSE,
                    target_notes TEXT
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                    price REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_game_type ON alerts(game_id, alert_type);

                CREATE TABLE IF NOT EXISTS retailers (
                    id SERIAL PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    check_interval_hours INTEGER NOT NULL DEFAULT 6,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE
                );

                CREATE TABLE IF NOT EXISTS physical_games (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'PS5',
                    edition TEXT NOT NULL DEFAULT 'Standard Edition',
                    target_price REAL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS physical_listings (
                    id SERIAL PRIMARY KEY,
                    physical_game_id INTEGER NOT NULL REFERENCES physical_games(id) ON DELETE CASCADE,
                    retailer_id INTEGER NOT NULL REFERENCES retailers(id) ON DELETE CASCADE,
                    product_url TEXT NOT NULL,
                    sku_or_asin TEXT,
                    seller_name TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    last_checked_at TIMESTAMP,
                    CONSTRAINT uq_game_retailer_url UNIQUE (physical_game_id, retailer_id, product_url)
                );

                CREATE TABLE IF NOT EXISTS physical_price_history (
                    id SERIAL PRIMARY KEY,
                    listing_id INTEGER NOT NULL REFERENCES physical_listings(id) ON DELETE CASCADE,
                    price REAL NOT NULL,
                    original_price REAL,
                    discount_percentage REAL DEFAULT 0.0,
                    in_stock BOOLEAN NOT NULL DEFAULT TRUE,
                    seller_name TEXT,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    checked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_phys_history_listing ON physical_price_history(listing_id, checked_at);

                CREATE TABLE IF NOT EXISTS physical_alerts (
                    id SERIAL PRIMARY KEY,
                    listing_id INTEGER NOT NULL REFERENCES physical_listings(id) ON DELETE CASCADE,
                    price REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS monitoring_runs (
                    id SERIAL PRIMARY KEY,
                    run_type TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    items_checked INTEGER DEFAULT 0,
                    successes INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    error_log TEXT
                );
                """)
                # Apply safe migrations to existing PostgreSQL tables
                self._migrate_postgres_columns(cursor)
            else:
                # SQLite schema
                cursor.executescript("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    store_id TEXT NOT NULL UNIQUE,
                    platform TEXT DEFAULT 'PS5',
                    store_url TEXT NOT NULL,
                    edition_name TEXT DEFAULT 'Standard Edition',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    original_price REAL,
                    discount_percentage REAL DEFAULT 0.0,
                    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                );
                CREATE INDEX IF NOT EXISTS idx_history_game_date
                    ON price_history(game_id, checked_at);
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL UNIQUE,
                    target_price REAL,
                    target_deal REAL,
                    target_great_deal REAL,
                    target_exceptional REAL,
                    is_provisional INTEGER NOT NULL DEFAULT 0,
                    target_notes TEXT,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id)
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_game_type
                    ON alerts(game_id, alert_type);

                CREATE TABLE IF NOT EXISTS retailers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    check_interval_hours INTEGER NOT NULL DEFAULT 6,
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS physical_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL DEFAULT 'PS5',
                    edition TEXT NOT NULL DEFAULT 'Standard Edition',
                    target_price REAL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS physical_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    physical_game_id INTEGER NOT NULL,
                    retailer_id INTEGER NOT NULL,
                    product_url TEXT NOT NULL,
                    sku_or_asin TEXT,
                    seller_name TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    last_checked_at TEXT,
                    FOREIGN KEY (physical_game_id) REFERENCES physical_games(id),
                    FOREIGN KEY (retailer_id) REFERENCES retailers(id),
                    UNIQUE(physical_game_id, retailer_id, product_url)
                );

                CREATE TABLE IF NOT EXISTS physical_price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    original_price REAL,
                    discount_percentage REAL DEFAULT 0.0,
                    in_stock INTEGER NOT NULL DEFAULT 1,
                    seller_name TEXT,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (listing_id) REFERENCES physical_listings(id)
                );
                CREATE INDEX IF NOT EXISTS idx_phys_history_listing
                    ON physical_price_history(listing_id, checked_at);

                CREATE TABLE IF NOT EXISTS physical_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    alert_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (listing_id) REFERENCES physical_listings(id)
                );

                CREATE TABLE IF NOT EXISTS monitoring_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TEXT,
                    items_checked INTEGER DEFAULT 0,
                    successes INTEGER DEFAULT 0,
                    failures INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    error_log TEXT
                );
                """)
                # Check for and apply migrations to pre-existing SQLite games and price_history tables
                self._migrate_sqlite_columns(cursor)

        # Seed standard Indian retailers
        self.seed_default_retailers()

    def _migrate_sqlite_columns(self, cursor):
        """Safely add new columns to existing SQLite tables if missing."""
        cursor.execute("PRAGMA table_info(games)")
        columns = [row[1] for row in cursor.fetchall()]
        if "edition_name" not in columns:
            cursor.execute("ALTER TABLE games ADD COLUMN edition_name TEXT DEFAULT 'Standard Edition'")
        if "is_active" not in columns:
            cursor.execute("ALTER TABLE games ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "created_at" not in columns:
            cursor.execute("ALTER TABLE games ADD COLUMN created_at TEXT")
            cursor.execute("UPDATE games SET created_at = datetime('now') WHERE created_at IS NULL")
        if "updated_at" not in columns:
            cursor.execute("ALTER TABLE games ADD COLUMN updated_at TEXT")
            cursor.execute("UPDATE games SET updated_at = datetime('now') WHERE updated_at IS NULL")

        cursor.execute("PRAGMA table_info(price_history)")
        price_cols = [row[1] for row in cursor.fetchall()]
        if "original_price" not in price_cols:
            cursor.execute("ALTER TABLE price_history ADD COLUMN original_price REAL")
        if "discount_percentage" not in price_cols:
            cursor.execute("ALTER TABLE price_history ADD COLUMN discount_percentage REAL DEFAULT 0.0")

        cursor.execute("PRAGMA table_info(watchlist)")
        wl_cols = [row[1] for row in cursor.fetchall()]
        if "target_deal" not in wl_cols:
            cursor.execute("ALTER TABLE watchlist ADD COLUMN target_deal REAL")
        if "target_great_deal" not in wl_cols:
            cursor.execute("ALTER TABLE watchlist ADD COLUMN target_great_deal REAL")
        if "target_exceptional" not in wl_cols:
            cursor.execute("ALTER TABLE watchlist ADD COLUMN target_exceptional REAL")
        if "is_provisional" not in wl_cols:
            cursor.execute("ALTER TABLE watchlist ADD COLUMN is_provisional INTEGER NOT NULL DEFAULT 0")
        if "target_notes" not in wl_cols:
            cursor.execute("ALTER TABLE watchlist ADD COLUMN target_notes TEXT")

    def _migrate_postgres_columns(self, cursor):
        """Safely add new columns to existing PostgreSQL tables if missing."""
        cursor.execute("""
            ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_deal REAL;
            ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_great_deal REAL;
            ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_exceptional REAL;
            ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS is_provisional BOOLEAN NOT NULL DEFAULT FALSE;
            ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS target_notes TEXT;
        """)

    def seed_default_retailers(self):
        """Ensure standard Indian retailers are registered with their respective check intervals."""
        default_retailers = [
            ("amazon_in", "Amazon India", "https://www.amazon.in/", 6),
            ("flipkart", "Flipkart", "https://www.flipkart.com/", 6),
            ("games_the_shop", "Games The Shop", "https://www.gamestheshop.com/", 12),
            ("games_shop_in", "Games Shop India", "https://www.gamesshop.in/", 12),
            ("playhq", "PlayHQ Games", "https://playhq.games/", 12),
        ]
        for code, name, base_url, interval in default_retailers:
            existing = self._fetchone("SELECT id FROM retailers WHERE code = ?", (code,))
            if not existing:
                self._execute(
                    "INSERT INTO retailers (code, name, base_url, check_interval_hours, is_active) VALUES (?, ?, ?, ?, ?)",
                    (code, name, base_url, interval, 1 if not self.use_postgres else True)
                )

    # -------------------------------------------------------------------------
    # DIGITAL GAME TRACKING METHODS
    # -------------------------------------------------------------------------

    def add_game(
        self,
        name: str,
        store_id: str,
        store_url: str,
        platform: str = "PS5",
        edition_name: str = "Standard Edition",
        is_active: bool = True
    ) -> int:
        """Add or update a digital game. If existing, updates metadata and re-activates monitoring."""
        active_val = is_active if self.use_postgres else (1 if is_active else 0)
        existing = self._fetchone("SELECT id FROM games WHERE store_id = ?", (store_id,))
        if existing:
            game_id = existing[0]
            self._execute(
                """
                UPDATE games
                SET name = ?, store_url = ?, platform = ?, edition_name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, store_url, platform, edition_name, active_val, game_id)
            )
            return game_id
        else:
            if self.use_postgres:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO games (name, store_id, store_url, platform, edition_name, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (name, store_id, store_url, platform, edition_name, is_active)
                    )
                    return cursor.fetchone()[0]
            else:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO games (name, store_id, store_url, platform, edition_name, is_active)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (name, store_id, store_url, platform, edition_name, active_val)
                    )
                    return cursor.lastrowid

    def get_game_by_id(self, game_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            "SELECT id, name, store_id, platform, store_url, edition_name, is_active FROM games WHERE id = ?",
            (game_id,)
        )
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "store_id": row[2],
            "platform": row[3],
            "store_url": row[4],
            "edition_name": row[5] or "Standard Edition",
            "is_active": bool(row[6]),
        }

    def get_game_by_store_id(self, store_id: str) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            "SELECT id, name, store_id, platform, store_url, edition_name, is_active FROM games WHERE store_id = ?",
            (store_id,)
        )
        if not row:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "store_id": row[2],
            "platform": row[3],
            "store_url": row[4],
            "edition_name": row[5] or "Standard Edition",
            "is_active": bool(row[6]),
        }

    def get_active_digital_games(self) -> List[Dict[str, Any]]:
        """Return all digital games with active monitoring."""
        rows = self._fetchall(
            """
            SELECT g.id, g.name, g.store_id, g.platform, g.store_url, g.edition_name,
                   w.target_price, w.target_deal, w.target_great_deal, w.target_exceptional,
                   w.is_provisional, w.target_notes
            FROM games g
            LEFT JOIN watchlist w ON g.id = w.game_id
            WHERE g.is_active = ?
            ORDER BY g.id ASC
            """,
            (True if self.use_postgres else 1,)
        )
        return [
            {
                "id": r[0],
                "name": r[1],
                "store_id": r[2],
                "platform": r[3],
                "store_url": r[4],
                "edition_name": r[5] or "Standard Edition",
                "target_price": r[6],
                "target_deal": r[7],
                "target_great_deal": r[8],
                "target_exceptional": r[9],
                "is_provisional": bool(r[10]) if r[10] is not None else False,
                "target_notes": r[11],
            }
            for r in rows
        ]

    def get_all_digital_games(self) -> List[Dict[str, Any]]:
        """Return all digital games including paused/inactive ones with their latest stats."""
        rows = self._fetchall(
            """
            SELECT g.id, g.name, g.store_id, g.platform, g.store_url, g.edition_name, g.is_active,
                   w.target_price, w.target_deal, w.target_great_deal, w.target_exceptional,
                   w.is_provisional, w.target_notes,
                   (SELECT price FROM price_history WHERE game_id = g.id ORDER BY id DESC LIMIT 1) as current_price,
                   (SELECT MIN(price) FROM price_history WHERE game_id = g.id) as historical_low,
                   (SELECT checked_at FROM price_history WHERE game_id = g.id ORDER BY id DESC LIMIT 1) as last_checked
            FROM games g
            LEFT JOIN watchlist w ON g.id = w.game_id
            ORDER BY g.id ASC
            """
        )
        return [
            {
                "id": r[0],
                "name": r[1],
                "store_id": r[2],
                "platform": r[3],
                "store_url": r[4],
                "edition_name": r[5] or "Standard Edition",
                "is_active": bool(r[6]),
                "target_price": r[7],
                "target_deal": r[8],
                "target_great_deal": r[9],
                "target_exceptional": r[10],
                "is_provisional": bool(r[11]) if r[11] is not None else False,
                "target_notes": r[12],
                "current_price": r[13],
                "historical_low": r[14],
                "last_checked": str(r[15]) if r[15] else None,
            }
            for r in rows
        ]

    def set_target_price(self, game_id: int, target_price: Optional[float]):
        """Set or update target price for a digital game (backwards-compatible)."""
        existing = self._fetchone("SELECT id FROM watchlist WHERE game_id = ?", (game_id,))
        if existing:
            self._execute(
                "UPDATE watchlist SET target_price = ?, target_exceptional = COALESCE(target_exceptional, ?) WHERE game_id = ?",
                (target_price, target_price, game_id)
            )
        else:
            self._execute(
                "INSERT INTO watchlist (game_id, target_price, target_exceptional) VALUES (?, ?, ?)",
                (game_id, target_price, target_price)
            )

    def set_target_tiers(
        self,
        game_id: int,
        target_deal: Optional[float] = None,
        target_great_deal: Optional[float] = None,
        target_exceptional: Optional[float] = None,
        is_provisional: bool = False,
        target_notes: Optional[str] = None
    ):
        """Set multi-tier target prices (DEAL, GREAT DEAL, EXCEPTIONAL) for a game."""
        legacy_target = target_exceptional if target_exceptional is not None else (target_great_deal or target_deal)
        existing = self._fetchone("SELECT id FROM watchlist WHERE game_id = ?", (game_id,))
        provisional_val = is_provisional if self.use_postgres else (1 if is_provisional else 0)

        if existing:
            self._execute(
                """
                UPDATE watchlist
                SET target_price = ?,
                    target_deal = ?,
                    target_great_deal = ?,
                    target_exceptional = ?,
                    is_provisional = ?,
                    target_notes = ?
                WHERE game_id = ?
                """,
                (legacy_target, target_deal, target_great_deal, target_exceptional, provisional_val, target_notes, game_id)
            )
        else:
            self._execute(
                """
                INSERT INTO watchlist (game_id, target_price, target_deal, target_great_deal, target_exceptional, is_provisional, target_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (game_id, legacy_target, target_deal, target_great_deal, target_exceptional, provisional_val, target_notes)
            )

    def get_target_tiers(self, game_id: int) -> Optional[Dict[str, Any]]:
        row = self._fetchone(
            "SELECT target_price, target_deal, target_great_deal, target_exceptional, is_provisional, target_notes FROM watchlist WHERE game_id = ?",
            (game_id,)
        )
        if not row:
            return None
        return {
            "target_price": row[0],
            "target_deal": row[1],
            "target_great_deal": row[2],
            "target_exceptional": row[3],
            "is_provisional": bool(row[4]) if row[4] is not None else False,
            "target_notes": row[5],
        }

    def get_target_price(self, game_id: int) -> Optional[float]:
        row = self._fetchone("SELECT target_price FROM watchlist WHERE game_id = ?", (game_id,))
        return row[0] if row else None

    def set_game_active_status(self, game_id: int, is_active: bool):
        """Enable or disable active monitoring without deleting history or settings."""
        active_val = is_active if self.use_postgres else (1 if is_active else 0)
        self._execute("UPDATE games SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (active_val, game_id))

    def get_historical_low(self, game_id: int) -> Optional[float]:
        """Return the lowest recorded price for a game, ignoring ₹0 if it was an anomalous free record."""
        row = self._fetchone(
            "SELECT MIN(price) FROM price_history WHERE game_id = ? AND price > 0",
            (game_id,)
        )
        return row[0] if row and row[0] is not None else None

    def save_price(
        self,
        game_id: int,
        price: float,
        currency: str = "INR",
        original_price: Optional[float] = None,
        discount_percentage: float = 0.0
    ):
        """Record a newly observed digital price."""
        self._execute(
            """
            INSERT INTO price_history (game_id, price, currency, original_price, discount_percentage)
            VALUES (?, ?, ?, ?, ?)
            """,
            (game_id, price, currency, original_price, discount_percentage)
        )

    def last_alert_price(self, game_id: int, alert_type: str) -> Optional[float]:
        row = self._fetchone(
            """
            SELECT price FROM alerts
            WHERE game_id = ? AND alert_type = ?
            ORDER BY id DESC LIMIT 1
            """,
            (game_id, alert_type)
        )
        return row[0] if row else None

    def record_alert(self, game_id: int, price: float, alert_type: str):
        """Record a sent alert to prevent duplicate notifications."""
        self._execute(
            "INSERT INTO alerts (game_id, price, alert_type) VALUES (?, ?, ?)",
            (game_id, price, alert_type)
        )

    # -------------------------------------------------------------------------
    # PHYSICAL DISC TRACKING METHODS
    # -------------------------------------------------------------------------

    def add_physical_game(
        self,
        title: str,
        platform: str = "PS5",
        edition: str = "Standard Edition",
        target_price: Optional[float] = None,
        is_active: bool = True
    ) -> int:
        active_val = is_active if self.use_postgres else (1 if is_active else 0)
        if self.use_postgres:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO physical_games (title, platform, edition, target_price, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (title, platform, edition, target_price, is_active)
                )
                return cursor.fetchone()[0]
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO physical_games (title, platform, edition, target_price, is_active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (title, platform, edition, target_price, active_val)
                )
                return cursor.lastrowid

    def add_physical_listing(
        self,
        physical_game_id: int,
        retailer_code: str,
        product_url: str,
        sku_or_asin: Optional[str] = None,
        seller_name: Optional[str] = None
    ) -> int:
        retailer = self._fetchone("SELECT id FROM retailers WHERE code = ?", (retailer_code,))
        if not retailer:
            raise ValueError(f"Unknown retailer code: {retailer_code}")
        retailer_id = retailer[0]

        existing = self._fetchone(
            "SELECT id FROM physical_listings WHERE physical_game_id = ? AND retailer_id = ? AND product_url = ?",
            (physical_game_id, retailer_id, product_url)
        )
        if existing:
            listing_id = existing[0]
            self._execute(
                """
                UPDATE physical_listings
                SET sku_or_asin = ?, seller_name = ?, is_active = ?
                WHERE id = ?
                """,
                (sku_or_asin, seller_name, True if self.use_postgres else 1, listing_id)
            )
            return listing_id

        if self.use_postgres:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO physical_listings (physical_game_id, retailer_id, product_url, sku_or_asin, seller_name, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (physical_game_id, retailer_id, product_url, sku_or_asin, seller_name, True)
                )
                return cursor.fetchone()[0]
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO physical_listings (physical_game_id, retailer_id, product_url, sku_or_asin, seller_name, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (physical_game_id, retailer_id, product_url, sku_or_asin, seller_name, 1)
                )
                return cursor.lastrowid

    def get_active_physical_listings(self) -> List[Dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT l.id, l.physical_game_id, g.title, g.platform, g.edition, g.target_price,
                   r.code as retailer_code, r.name as retailer_name, r.check_interval_hours,
                   l.product_url, l.sku_or_asin, l.seller_name, l.last_checked_at
            FROM physical_listings l
            JOIN physical_games g ON l.physical_game_id = g.id
            JOIN retailers r ON l.retailer_id = r.id
            WHERE l.is_active = ? AND g.is_active = ? AND r.is_active = ?
            ORDER BY g.id ASC, r.id ASC
            """,
            (True if self.use_postgres else 1, True if self.use_postgres else 1, True if self.use_postgres else 1)
        )
        return [
            {
                "listing_id": r[0],
                "physical_game_id": r[1],
                "title": r[2],
                "platform": r[3],
                "edition": r[4],
                "target_price": r[5],
                "retailer_code": r[6],
                "retailer_name": r[7],
                "check_interval_hours": r[8],
                "product_url": r[9],
                "sku_or_asin": r[10],
                "seller_name": r[11],
                "last_checked_at": str(r[12]) if r[12] else None,
            }
            for r in rows
        ]

    def save_physical_price(
        self,
        listing_id: int,
        price: float,
        original_price: Optional[float] = None,
        discount_percentage: float = 0.0,
        in_stock: bool = True,
        seller_name: Optional[str] = None,
        currency: str = "INR"
    ):
        stock_val = in_stock if self.use_postgres else (1 if in_stock else 0)
        self._execute(
            """
            INSERT INTO physical_price_history (listing_id, price, original_price, discount_percentage, in_stock, seller_name, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (listing_id, price, original_price, discount_percentage, stock_val, seller_name, currency)
        )
        self._execute(
            "UPDATE physical_listings SET last_checked_at = CURRENT_TIMESTAMP WHERE id = ?",
            (listing_id,)
        )

    def get_physical_historical_low(self, physical_game_id: int) -> Optional[float]:
        row = self._fetchone(
            """
            SELECT MIN(h.price)
            FROM physical_price_history h
            JOIN physical_listings l ON h.listing_id = l.id
            WHERE l.physical_game_id = ? AND h.price > 0 AND h.in_stock = ?
            """,
            (physical_game_id, True if self.use_postgres else 1)
        )
        return row[0] if row and row[0] is not None else None

    def last_physical_alert_price(self, listing_id: int, alert_type: str) -> Optional[float]:
        row = self._fetchone(
            """
            SELECT price FROM physical_alerts
            WHERE listing_id = ? AND alert_type = ?
            ORDER BY id DESC LIMIT 1
            """,
            (listing_id, alert_type)
        )
        return row[0] if row else None

    def record_physical_alert(self, listing_id: int, price: float, alert_type: str):
        self._execute(
            "INSERT INTO physical_alerts (listing_id, price, alert_type) VALUES (?, ?, ?)",
            (listing_id, price, alert_type)
        )

    # -------------------------------------------------------------------------
    # MONITORING RUN LOGS
    # -------------------------------------------------------------------------

    def start_monitoring_run(self, run_type: str) -> int:
        if self.use_postgres:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO monitoring_runs (run_type, status) VALUES (%s, %s) RETURNING id",
                    (run_type, "running")
                )
                return cursor.fetchone()[0]
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO monitoring_runs (run_type, status) VALUES (?, ?)",
                    (run_type, "running")
                )
                return cursor.lastrowid

    def finish_monitoring_run(
        self,
        run_id: int,
        items_checked: int,
        successes: int,
        failures: int,
        status: str,
        error_log: Optional[str] = None
    ):
        self._execute(
            """
            UPDATE monitoring_runs
            SET finished_at = CURRENT_TIMESTAMP, items_checked = ?, successes = ?, failures = ?, status = ?, error_log = ?
            WHERE id = ?
            """,
            (items_checked, successes, failures, status, error_log, run_id)
        )


# Global default database instance (auto-detects PostgreSQL or SQLite)
db = Database()

# Functional export aliases matching existing code
def initialize_database():
    db.initialize_database()

def add_game(name, store_id, store_url, platform="PS5", edition_name="Standard Edition", is_active=True):
    return db.add_game(name, store_id, store_url, platform, edition_name, is_active)

def set_target_price(game_id, target_price):
    db.set_target_price(game_id, target_price)

def get_target_price(game_id):
    return db.get_target_price(game_id)

def get_historical_low(game_id):
    return db.get_historical_low(game_id)

def save_price(game_id, price, currency="INR", original_price=None, discount_percentage=0.0):
    db.save_price(game_id, price, currency, original_price, discount_percentage)

def last_alert_price(game_id, alert_type):
    return db.last_alert_price(game_id, alert_type)

def record_alert(game_id, price, alert_type):
    db.record_alert(game_id, price, alert_type)
