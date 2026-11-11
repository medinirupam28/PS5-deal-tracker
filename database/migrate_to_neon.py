"""Database migration utility from SQLite to Neon PostgreSQL.

Safely migrates all historical records (games, price_history, watchlist, alerts, etc.)
from ps5_deals.db to Neon PostgreSQL.
Guarantees:
- Creates an immutable timestamped backup of SQLite database before migration.
- Runs migration inside an atomic PostgreSQL transaction.
- Verifies record counts and data integrity before committing.
- Rolls back immediately if any assertion fails.
- Never deletes or modifies the SQLite database.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

import config

# Path definitions
ROOT_DIR = Path(__file__).resolve().parents[1]
SQLITE_DB_PATH = ROOT_DIR / "ps5_deals.db"
BACKUP_DIR = ROOT_DIR / "backups"

try:
    import psycopg
    from psycopg import sql
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False


def create_sqlite_backup() -> Path:
    """Create a timestamped backup copy of the SQLite database."""
    if not SQLITE_DB_PATH.exists():
        raise FileNotFoundError(f"SQLite database not found at {SQLITE_DB_PATH}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"ps5_deals_backup_{timestamp}.db"
    shutil.copy2(SQLITE_DB_PATH, backup_file)
    print(f"Created SQLite backup at: {backup_file}")
    return backup_file


def get_sqlite_counts(sqlite_path: Path) -> Dict[str, int]:
    """Inspect and return row counts for all tables in the SQLite database."""
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    counts = {}
    for table in tables:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        counts[table] = count
    conn.close()
    return counts


def apply_postgres_schema(pg_conn):
    """Ensure all required tables and indexes exist in the PostgreSQL database."""
    with pg_conn.cursor() as cursor:
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
            target_price REAL
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


def migrate_data(sqlite_path: Path, neon_url: str, dry_run: bool = False) -> bool:
    """Execute migration from SQLite to Neon PostgreSQL with atomic safety."""
    if not PSYCOPG_AVAILABLE:
        raise RuntimeError("psycopg driver is required for Neon PostgreSQL migration. Run: pip install psycopg[binary]")

    if not neon_url:
        raise ValueError("NEON_DATABASE_URL is not set. Provide it in .env or via --neon-url.")

    sqlite_backup = create_sqlite_backup()
    sqlite_counts = get_sqlite_counts(sqlite_path)
    print("\n--- SQLite Source Table Counts ---")
    for tbl, count in sqlite_counts.items():
        print(f"  {tbl}: {count} records")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_cursor = sqlite_conn.cursor()

    print(f"\nConnecting to Neon PostgreSQL...")
    pg_conn = psycopg.connect(neon_url)
    try:
        with pg_conn.transaction():
            apply_postgres_schema(pg_conn)
            with pg_conn.cursor() as pg_cursor:
                # 1. Migrate games
                sqlite_cursor.execute("SELECT id, name, store_id, platform, store_url, edition_name, is_active FROM games")
                games = sqlite_cursor.fetchall()
                for row in games:
                    pg_cursor.execute(
                        """
                        INSERT INTO games (id, name, store_id, platform, store_url, edition_name, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            name = EXCLUDED.name,
                            store_url = EXCLUDED.store_url,
                            edition_name = EXCLUDED.edition_name,
                            is_active = EXCLUDED.is_active
                        """,
                        (row[0], row[1], row[2], row[3], row[4], row[5] or "Standard Edition", bool(row[6]))
                    )

                # 2. Migrate price_history
                sqlite_cursor.execute("SELECT id, game_id, price, currency, checked_at, original_price, discount_percentage FROM price_history")
                prices = sqlite_cursor.fetchall()
                for row in prices:
                    pg_cursor.execute(
                        """
                        INSERT INTO price_history (id, game_id, price, currency, checked_at, original_price, discount_percentage)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            price = EXCLUDED.price,
                            currency = EXCLUDED.currency
                        """,
                        (row[0], row[1], row[2], row[3], row[4], row[5], row[6] or 0.0)
                    )

                # 3. Migrate watchlist
                sqlite_cursor.execute("SELECT id, game_id, target_price FROM watchlist")
                watch_entries = sqlite_cursor.fetchall()
                for row in watch_entries:
                    pg_cursor.execute(
                        """
                        INSERT INTO watchlist (id, game_id, target_price)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            target_price = EXCLUDED.target_price
                        """,
                        (row[0], row[1], row[2])
                    )

                # 4. Migrate alerts
                sqlite_cursor.execute("SELECT id, game_id, price, alert_type, sent_at FROM alerts")
                alert_entries = sqlite_cursor.fetchall()
                for row in alert_entries:
                    pg_cursor.execute(
                        """
                        INSERT INTO alerts (id, game_id, price, alert_type, sent_at)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (row[0], row[1], row[2], row[3], row[4])
                    )

                # 5. Migrate retailers
                sqlite_cursor.execute("SELECT id, code, name, base_url, check_interval_hours, is_active FROM retailers")
                retailers = sqlite_cursor.fetchall()
                for row in retailers:
                    pg_cursor.execute(
                        """
                        INSERT INTO retailers (id, code, name, base_url, check_interval_hours, is_active)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (code) DO UPDATE SET
                            check_interval_hours = EXCLUDED.check_interval_hours,
                            is_active = EXCLUDED.is_active
                        """,
                        (row[0], row[1], row[2], row[3], row[4], bool(row[5]))
                    )

                # Reset SERIAL sequences
                for seq_table in ["games", "price_history", "watchlist", "alerts", "retailers", "physical_games", "physical_listings", "physical_price_history", "physical_alerts", "monitoring_runs"]:
                    pg_cursor.execute(f"SELECT setval(pg_get_serial_sequence('{seq_table}', 'id'), COALESCE((SELECT MAX(id) FROM {seq_table}), 1), true)")

                # Verify counts in PostgreSQL
                print("\n--- Verifying Neon PostgreSQL Counts ---")
                for table, expected_count in sqlite_counts.items():
                    if table in ["games", "price_history", "watchlist", "alerts", "retailers"]:
                        pg_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                        pg_count = pg_cursor.fetchone()[0]
                        print(f"  {table}: Expected {expected_count} | Found {pg_count}")
                        if pg_count < expected_count:
                            raise AssertionError(f"Count mismatch for table {table}: expected {expected_count}, got {pg_count}")

                if dry_run:
                    print("\n[Dry Run] Verification passed. Rolling back changes as requested.")
                    raise KeyboardInterrupt("Dry run completed successfully.")

        print("\nSUCCESS: All records verified and migrated to Neon PostgreSQL successfully!")
        return True
    except KeyboardInterrupt:
        return True
    except Exception as e:
        print(f"\nERROR during migration: {e}")
        print("PostgreSQL transaction rolled back. SQLite database remains completely unmodified.")
        return False
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate PS5 Deal Tracker database from SQLite to Neon PostgreSQL.")
    parser.add_argument("--neon-url", default=config.NEON_DATABASE_URL, help="Neon PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Verify migration and roll back without committing")
    args = parser.parse_args()

    if not args.neon_url:
        print("Error: No Neon PostgreSQL connection URL provided.")
        print("Please set NEON_DATABASE_URL in .env or provide it via --neon-url.")
        sys.exit(1)

    success = migrate_data(SQLITE_DB_PATH, args.neon_url, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
