"""Main entry point for Digital PS5 Game Price Monitoring.

Supports:
- Running once (--once) for GitHub Actions or manual triggers.
- Continuous scheduled monitoring (every 2 hours by default).
- Dynamic database-backed watchlist with edition disambiguation.
- Detailed run logging into monitoring_runs table.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import config
from collector.apish_collector import APISHCollector
from database.db import db
from analyzer.deal_detector import detect_deal
from notifications.telegram import send_deal_alert
from scheduler.schedule import start_scheduler

ROOT = Path(__file__).resolve().parent
WATCHLIST_PATH = ROOT / "watchlist.json"


def load_initial_watchlist_settings() -> Dict[str, Any]:
    if WATCHLIST_PATH.exists():
        with WATCHLIST_PATH.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {
        "region": config.DEFAULT_REGION,
        "currency": config.DEFAULT_CURRENCY,
        "check_interval_hours": config.DEFAULT_CHECK_INTERVAL_HOURS,
        "minimum_discount_percent": config.DEFAULT_MINIMUM_DISCOUNT,
        "games": []
    }


def monitor_digital_games():
    """Execute a single monitoring cycle across all active digital games."""
    db.initialize_database()
    settings = load_initial_watchlist_settings()
    min_discount = settings.get("minimum_discount_percent", config.DEFAULT_MINIMUM_DISCOUNT)

    # Get active digital games from database
    active_games = db.get_active_digital_games()

    # If database has no games yet, seed from watchlist.json
    if not active_games and settings.get("games"):
        print("Database games list empty. Seeding from watchlist.json...")
        for g in settings["games"]:
            gid = db.add_game(
                name=g["name"],
                store_id=g["store_id"],
                store_url=g["store_url"],
                platform="PS5",
                edition_name="Standard Edition",
                is_active=True
            )
            if g.get("target_price") is not None:
                db.set_target_price(gid, g["target_price"])
        active_games = db.get_active_digital_games()

    if not active_games:
        print("No active digital games in watchlist. Use 'py manage_watchlist.py add <url>' to add games.")
        return

    run_id = db.start_monitoring_run("digital")
    collector = APISHCollector(region=settings.get("region", config.DEFAULT_REGION))
    print(f"\nChecking Indian PlayStation Store prices for {len(active_games)} active game(s)...")

    successes = 0
    failures = 0

    for game in active_games:
        game_id = game["id"]
        game_name = game["name"]
        try:
            # allow_free=False ensures paid games never resolve to 0.0 free-to-play packages
            price = collector.get_game_price(game, allow_free=False)

            if price["currency"] != "INR":
                raise ValueError(f"Expected INR display price, got {price['currency']}")

            # Update edition name if detected
            if price.get("edition_name"):
                db.add_game(
                    name=game_name,
                    store_id=game["store_id"],
                    store_url=game["store_url"],
                    platform=game.get("platform", "PS5"),
                    edition_name=price["edition_name"],
                    is_active=True
                )

            # Deal detection
            detection = detect_deal(
                game_id=game_id,
                current_price=price["current_price"],
                original_price=price["original_price"],
                target_price=game.get("target_price"),
                minimum_discount=min_discount,
            )

            print(
                f"OK     | {game_name} | {price['edition_name']} | "
                f"₹{price['current_price']:,.0f} | {price.get('discount_text') or 'No discount'}"
            )

            if detection:
                sent = send_deal_alert(game, price, detection)
                if sent:
                    for alert_type in detection["alert_types"]:
                        db.record_alert(game_id, price["current_price"], alert_type)
                    print("  Telegram alert sent.")
                else:
                    print("  Alert condition found, but Telegram notification did not deliver.")

            # Record price history
            db.save_price(
                game_id=game_id,
                price=price["current_price"],
                currency="INR",
                original_price=price["original_price"],
                discount_percentage=detection["discount_percentage"] if detection else 0.0
            )
            successes += 1

        except Exception as exc:
            failures += 1
            print(f"FAILED | {game_name} | {type(exc).__name__}: {exc}")

    status_str = "success" if failures == 0 else ("partial" if successes > 0 else "failed")
    summary = f"Cycle finished: {successes} successful, {failures} failed."
    print(f"\n{summary}")

    db.finish_monitoring_run(
        run_id=run_id,
        items_checked=len(active_games),
        successes=successes,
        failures=failures,
        status=status_str,
        error_log=summary if failures > 0 else None
    )


def main():
    parser = argparse.ArgumentParser(description="PS5 Digital Game Deal Monitor")
    parser.add_argument("--once", action="store_true", help="Run a single monitoring cycle and exit")
    args = parser.parse_args()

    if not config.is_apish_configured():
        sys.exit("APISH_KEY missing. Copy .env.example to .env and add your API key.")

    if args.once:
        monitor_digital_games()
    else:
        settings = load_initial_watchlist_settings()
        interval = int(settings.get("check_interval_hours", config.DEFAULT_CHECK_INTERVAL_HOURS))
        start_scheduler(monitor_digital_games, interval)


if __name__ == "__main__":
    main()
