"""Physical PS5 Game Disc Price Monitoring Cycle.

Iterates over registered physical disc listings across authorized Indian retailers.
Adheres strictly to compliance rules:
- Prohibits unauthorized web scraping and CAPTCHA solving.
- Never records mock or fake prices.
- Checks configurable retailer intervals.
- Detects cross-retailer historical lows and target price hits.
- Dispatches Telegram notifications without duplicate spam.
"""

import sys
from datetime import datetime, timezone
from typing import Dict, Any

import config
from collector.retailers.registry import retailer_registry
from collector.retailers.base import RetailerStatus
from database.db import db
from analyzer.deal_detector import detect_physical_deal
from notifications.telegram import send_physical_deal_alert


def run_physical_monitoring():
    print("\n" + "=" * 60)
    print("Starting Physical PS5 Disc Price Monitoring Cycle")
    print("=" * 60)

    db.initialize_database()
    run_id = db.start_monitoring_run("physical")

    listings = db.get_active_physical_listings()
    if not listings:
        print("No active physical disc listings found in database.")
        print("Add physical listings using: py manage_watchlist.py add-physical ...")
        db.finish_monitoring_run(
            run_id=run_id,
            items_checked=0,
            successes=0,
            failures=0,
            status="success",
            error_log="No active physical listings registered."
        )
        return

    successes = 0
    failures = 0
    skipped_compliance = 0

    for item in listings:
        game_title = item["title"]
        retailer_name = item["retailer_name"]
        retailer_code = item["retailer_code"]
        product_url = item["product_url"]
        listing_id = item["listing_id"]
        physical_game_id = item["physical_game_id"]
        target_price = item["target_price"]

        provider = retailer_registry.get_provider(retailer_code)
        if not provider:
            print(f"FAILED | {game_title} | {retailer_name}: Unknown retailer code '{retailer_code}'")
            failures += 1
            continue

        status = provider.get_status()
        if status == RetailerStatus.CREDENTIALS_REQUIRED:
            print(f"SKIP   | {game_title} | {retailer_name}: Credentials required ({provider.get_status_message()})")
            skipped_compliance += 1
            continue
        elif status == RetailerStatus.UNAVAILABLE:
            print(f"SKIP   | {game_title} | {retailer_name}: Automated collection unavailable per retailer terms")
            skipped_compliance += 1
            continue

        # If provider is ACTIVE, attempt fetch
        try:
            result = provider.fetch_price(product_url, sku=item.get("sku_or_asin"))
            if not result.success:
                print(f"FAILED | {game_title} | {retailer_name}: {result.error_message}")
                failures += 1
                continue

            if result.price is None or result.price <= 0:
                print(f"FAILED | {game_title} | {retailer_name}: Invalid or zero price returned")
                failures += 1
                continue

            # Record verified live price
            db.save_physical_price(
                listing_id=listing_id,
                price=result.price,
                original_price=result.original_price,
                discount_percentage=result.discount_percentage,
                in_stock=result.in_stock,
                seller_name=result.seller_name or item.get("seller_name"),
                currency=result.currency
            )

            # Deal detection
            detection = detect_physical_deal(
                physical_game_id=physical_game_id,
                listing_id=listing_id,
                current_price=result.price,
                original_price=result.original_price,
                target_price=target_price,
                minimum_discount=20.0
            )

            print(f"OK     | {game_title} | {retailer_name} | ₹{result.price:,.0f} | In Stock: {result.in_stock}")

            if detection:
                sent = send_physical_deal_alert(
                    item={
                        "title": game_title,
                        "retailer_name": retailer_name,
                        "product_url": product_url,
                        "seller_name": result.seller_name or item.get("seller_name") or "Retailer Direct",
                    },
                    price_data={
                        "current_price": result.price,
                        "original_price": result.original_price,
                    },
                    detection=detection
                )
                if sent:
                    for alert_type in detection["alert_types"]:
                        db.record_physical_alert(listing_id, result.price, alert_type)
                    print("  Telegram alert sent.")
                else:
                    print("  Alert condition met, but Telegram notification was not dispatched.")

            successes += 1

        except Exception as exc:
            failures += 1
            print(f"ERROR  | {game_title} | {retailer_name}: {type(exc).__name__}: {exc}")

    overall_status = "success" if failures == 0 else ("partial" if successes > 0 else "failed")
    summary = f"Physical cycle finished: {successes} checked, {skipped_compliance} skipped compliance, {failures} failed."
    print("\n" + summary)

    db.finish_monitoring_run(
        run_id=run_id,
        items_checked=len(listings),
        successes=successes,
        failures=failures,
        status=overall_status,
        error_log=summary if failures > 0 else None
    )


if __name__ == "__main__":
    run_physical_monitoring()
