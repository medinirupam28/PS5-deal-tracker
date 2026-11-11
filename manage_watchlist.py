"""Watchlist Management CLI for PS5 Digital and Physical Games.

Provides user-friendly commands to:
- Digital: Add games by PS Store URLs with edition selection and free-to-play protection.
- Digital: View, edit target prices, pause, resume, and remove games without deleting history.
- Physical: Add physical PS5 games, link multiple retailer URLs (Amazon, Flipkart, etc.).
- Physical: View retailer integration statuses and compliance information.
- Export and import watchlists in validated JSON format.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from collector.apish_collector import APISHCollector, extract_store_id, validate_store_url
from collector.retailers.registry import retailer_registry
from database.db import db


# -----------------------------------------------------------------------------
# DIGITAL WATCHLIST COMMANDS
# -----------------------------------------------------------------------------

def cmd_add(args):
    url = args.url.strip()
    if not validate_store_url(url):
        print(f"Error: '{url}' is not a valid Indian PlayStation Store URL.")
        print("Expected URL format: https://store.playstation.com/en-in/concept/<id> or .../product/<id>")
        return 1

    if not config.APISH_KEY:
        print("Error: APISH_KEY is missing from .env. Please configure your API.SH key.")
        return 1

    print(f"\nInspecting PlayStation Store: {url}")
    collector = APISHCollector(region="en-in")
    try:
        editions = collector.get_available_editions(url)
    except Exception as exc:
        print(f"Failed to fetch store details: {exc}")
        return 1

    if not editions:
        print("No editions found for this URL.")
        return 1

    game_title = editions[0]["game_name"]
    print(f"\n🎮 Game Identified: {game_title}")
    print(f"Found {len(editions)} available edition(s):\n")

    for idx, ed in enumerate(editions, start=1):
        price_str = f"₹{ed['current_price']:,.0f}" if ed['current_price'] is not None else "Price not listed"
        free_badge = " [FREE/TRIAL]" if ed["is_free"] else ""
        ps5_badge = " [PS5]" if ed["is_ps5"] else ""
        print(f"  [{idx}] {ed['edition_name']}{ps5_badge}{free_badge} — {price_str} (ID: {ed['edition_id'] or 'N/A'})")

    # Select edition
    selected_edition = None
    if args.edition_id:
        for ed in editions:
            if ed["edition_id"] == args.edition_id:
                selected_edition = ed
                break
        if not selected_edition:
            print(f"Error: Edition ID '{args.edition_id}' not found among available editions.")
            return 1
    elif args.edition:
        try:
            choice_idx = int(args.edition) - 1
            if 0 <= choice_idx < len(editions):
                selected_edition = editions[choice_idx]
        except ValueError:
            for ed in editions:
                if args.edition.lower() in ed["edition_name"].lower():
                    selected_edition = ed
                    break
        if not selected_edition:
            print(f"Error: Specified edition '{args.edition}' was not found.")
            return 1
    elif len(editions) == 1:
        selected_edition = editions[0]
    else:
        while True:
            try:
                choice = input(f"\nSelect edition to track [1-{len(editions)}] (or 'q' to cancel): ").strip()
                if choice.lower() == 'q':
                    print("Cancelled.")
                    return 0
                idx = int(choice) - 1
                if 0 <= idx < len(editions):
                    selected_edition = editions[idx]
                    break
                print(f"Invalid choice. Please enter a number between 1 and {len(editions)}.")
            except (ValueError, KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                return 0

    if selected_edition["is_free"] and not args.allow_free:
        print(f"\n⚠️ WARNING: '{selected_edition['edition_name']}' is listed as FREE or a demo/trial.")
        if not args.yes:
            confirm_free = input("Are you sure you want to track this free item instead of a paid game? [y/N]: ").strip().lower()
            if confirm_free != 'y':
                print("Aborted addition. Please choose the full paid PS5 edition.")
                return 0

    target_price = args.target
    if target_price is None and not args.yes:
        try:
            target_input = input(f"Enter target price in INR for {selected_edition['edition_name']} (or press Enter to skip): ").strip()
            if target_input:
                target_price = float(target_input.replace("₹", "").replace(",", ""))
        except ValueError:
            print("Invalid target price number. Skipping target price.")
            target_price = None

    store_id = selected_edition["edition_id"] or extract_store_id(url)
    if not store_id:
        store_id = url

    print("\n--- Summary to Add ---")
    print(f"  Title:        {game_title}")
    print(f"  Edition:      {selected_edition['edition_name']}")
    print(f"  Product ID:   {store_id}")
    print(f"  Current:      {'₹{:,.0f}'.format(selected_edition['current_price']) if selected_edition['current_price'] is not None else 'N/A'}")
    print(f"  Target Price: {'₹{:,.0f}'.format(target_price) if target_price else 'None'}")
    print(f"  Store URL:    {selected_edition['store_url']}")

    if not args.yes:
        confirm = input("\nSave this game to your active watchlist? [Y/n]: ").strip().lower()
        if confirm in ('n', 'no'):
            print("Cancelled.")
            return 0

    existing = db.get_game_by_store_id(store_id)
    if existing:
        game_id = existing["id"]
        db.add_game(
            name=game_title,
            store_id=store_id,
            store_url=selected_edition["store_url"],
            platform="PS5",
            edition_name=selected_edition["edition_name"],
            is_active=True
        )
        if target_price is not None:
            db.set_target_price(game_id, target_price)
        print(f"\n✅ Reconnected to existing tracked game (ID: {game_id}). Historical price points preserved!")
    else:
        game_id = db.add_game(
            name=game_title,
            store_id=store_id,
            store_url=selected_edition["store_url"],
            platform="PS5",
            edition_name=selected_edition["edition_name"],
            is_active=True
        )
        if target_price is not None:
            db.set_target_price(game_id, target_price)
        if selected_edition["current_price"] is not None:
            db.save_price(game_id, selected_edition["current_price"], "INR", selected_edition["original_price"])
        print(f"\n✅ Successfully added '{game_title}' to watchlist (ID: {game_id})!")

    return 0


def cmd_list(args):
    games = db.get_all_digital_games()
    if not games:
        print("Your digital watchlist is empty. Add a game with: py manage_watchlist.py add <store_url>")
        return 0

    print(f"\n{'ID':<4} {'Title':<30} {'Edition':<25} {'Current':<10} {'Target':<10} {'Hist Low':<10} {'Status':<8} {'Last Checked':<19}")
    print("-" * 122)
    for g in games:
        curr = f"₹{g['current_price']:,.0f}" if g["current_price"] is not None else "Pending"
        target = f"₹{g['target_price']:,.0f}" if g["target_price"] is not None else "None"
        low = f"₹{g['historical_low']:,.0f}" if g["historical_low"] is not None else "N/A"
        status = "ACTIVE" if g["is_active"] else "PAUSED"
        checked = str(g["last_checked"])[:19] if g["last_checked"] else "Never"
        title = g["name"][:28] + ".." if len(g["name"]) > 30 else g["name"]
        edition = (g["edition_name"] or "Standard")[:23] + ".." if len(g["edition_name"] or "") > 25 else (g["edition_name"] or "Standard")
        print(f"{g['id']:<4} {title:<30} {edition:<25} {curr:<10} {target:<10} {low:<10} {status:<8} {checked:<19}")
    print("-" * 122)
    print(f"Total: {len(games)} game(s) ({sum(1 for g in games if g['is_active'])} active, {sum(1 for g in games if not g['is_active'])} paused)\n")
    return 0


def cmd_target(args):
    game = db.get_game_by_id(args.id)
    if not game:
        print(f"Error: Game ID {args.id} not found in database.")
        return 1

    try:
        price = float(args.price.replace("₹", "").replace(",", ""))
    except ValueError:
        print("Error: Target price must be a valid number in INR.")
        return 1

    db.set_target_price(args.id, price)
    print(f"✅ Updated target price for '{game['name']}' (ID: {args.id}) to ₹{price:,.0f}.")
    return 0


def cmd_toggle(args):
    game = db.get_game_by_id(args.id)
    if not game:
        print(f"Error: Game ID {args.id} not found in database.")
        return 1

    new_status = not game["is_active"]
    if args.enable:
        new_status = True
    elif args.disable:
        new_status = False

    db.set_game_active_status(args.id, new_status)
    status_str = "ACTIVE (Monitoring Resumed)" if new_status else "PAUSED (Monitoring Suspended)"
    print(f"✅ Set '{game['name']}' (ID: {args.id}) monitoring to: {status_str}.")
    print("   Note: All historical price records and target prices remain safely preserved.")
    return 0


def cmd_remove(args):
    game = db.get_game_by_id(args.id)
    if not game:
        print(f"Error: Game ID {args.id} not found in database.")
        return 1

    if not args.yes:
        confirm = input(f"Remove '{game['name']}' from active monitoring? All history will be preserved. [y/N]: ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            return 0

    db.set_game_active_status(args.id, False)
    print(f"✅ Removed '{game['name']}' (ID: {args.id}) from active monitoring.")
    print("   All historical price observations and alert logs remain safely preserved in the database.")
    return 0


def cmd_export(args):
    output_path = Path(args.output)
    games = db.get_all_digital_games()
    export_data = {
        "region": "en-in",
        "currency": "INR",
        "exported_count": len(games),
        "games": [
            {
                "name": g["name"],
                "edition_name": g["edition_name"],
                "store_id": g["store_id"],
                "store_url": g["store_url"],
                "target_price": g["target_price"],
                "is_active": g["is_active"],
            }
            for g in games
        ]
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Exported {len(games)} watchlist games to: {output_path}")
    return 0


def cmd_import(args):
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"Error: File '{input_path}' not found.")
        return 1

    with input_path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as exc:
            print(f"Error: Failed to parse JSON file: {exc}")
            return 1

    items = data.get("games", [])
    if not items:
        print("No 'games' array found in the import file.")
        return 1

    imported = 0
    reconnected = 0
    for item in items:
        name = item.get("name")
        store_id = item.get("store_id")
        store_url = item.get("store_url")
        edition_name = item.get("edition_name") or "Standard Edition"
        target_price = item.get("target_price")
        is_active = item.get("is_active", True)

        if not store_id or not store_url:
            continue

        existing = db.get_game_by_store_id(store_id)
        if existing:
            reconnected += 1
        else:
            imported += 1

        gid = db.add_game(name, store_id, store_url, "PS5", edition_name, is_active)
        if target_price is not None:
            db.set_target_price(gid, target_price)

    print(f"✅ Import completed: {imported} new games added, {reconnected} existing games updated/reconnected.")
    return 0


# -----------------------------------------------------------------------------
# PHYSICAL DISC COMMANDS
# -----------------------------------------------------------------------------

def cmd_retailers(args):
    """Display status of all supported Indian retailers."""
    statuses = retailer_registry.get_status_summary()
    print(f"\n{'Retailer':<18} {'Code':<15} {'Interval':<10} {'Status':<22} {'Compliance & Integration Notes'}")
    print("-" * 115)
    for s in statuses:
        print(f"{s['name']:<18} {s['code']:<15} {s['check_interval_hours'] + 'h':<10} {s['status']:<22} {s['message'][:45]}...")
    print("-" * 115)
    return 0


def cmd_add_physical(args):
    """Add a physical PS5 game disc to track."""
    title = args.title.strip()
    edition = args.edition or "Standard Edition"
    target_price = args.target

    game_id = db.add_physical_game(
        title=title,
        platform="PS5",
        edition=edition,
        target_price=target_price,
        is_active=True
    )
    print(f"✅ Added physical PS5 game: '{title}' ({edition}) [ID: {game_id}]")

    if args.url:
        provider = retailer_registry.identify_provider_for_url(args.url)
        if not provider:
            print(f"Warning: Could not automatically detect retailer for URL: {args.url}")
            print("Please link the retailer URL manually using: py manage_watchlist.py add-listing ...")
        else:
            listing_id = db.add_physical_listing(
                physical_game_id=game_id,
                retailer_code=provider.code,
                product_url=args.url,
                sku_or_asin=args.sku,
                seller_name=args.seller
            )
            print(f"   Linked {provider.name} listing [ID: {listing_id}].")

    return 0


def cmd_add_listing(args):
    """Link a retailer product URL to an existing physical game."""
    game_id = args.game_id
    url = args.url.strip()

    provider = retailer_registry.identify_provider_for_url(url)
    retailer_code = args.retailer or (provider.code if provider else None)
    if not retailer_code:
        print("Error: Could not identify retailer from URL. Please specify --retailer <code/name> explicitly.")
        return 1

    listing_id = db.add_physical_listing(
        physical_game_id=game_id,
        retailer_code=retailer_code,
        product_url=url,
        sku_or_asin=args.sku,
        seller_name=args.seller
    )
    print(f"✅ Linked {retailer_code} listing [ID: {listing_id}] to physical game ID {game_id}.")
    return 0


def cmd_list_physical(args):
    """List all registered physical game listings."""
    listings = db.get_active_physical_listings()
    if not listings:
        print("No active physical game listings found. Add one with: py manage_watchlist.py add-physical 'Game Title'")
        return 0

    print(f"\n{'Listing ID':<11} {'Game Title':<28} {'Retailer':<16} {'Target':<10} {'Seller':<16} {'Product URL'}")
    print("-" * 115)
    for item in listings:
        target = f"₹{item['target_price']:,.0f}" if item["target_price"] is not None else "None"
        seller = item["seller_name"] or "Direct"
        url = item["product_url"][:40] + "..." if len(item["product_url"]) > 40 else item["product_url"]
        print(f"{item['listing_id']:<11} {item['title'][:26]:<28} {item['retailer_name']:<16} {target:<10} {seller:<16} {url}")
    print("-" * 115)
    return 0


def main():
    parser = argparse.ArgumentParser(description="PS5 Digital & Physical Watchlist Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # DIGITAL COMMANDS
    p_add = subparsers.add_parser("add", help="Add a game by PlayStation Store URL")
    p_add.add_argument("url", help="PlayStation Store URL (en-in)")
    p_add.add_argument("--edition", help="Edition number (1-N) or name keyword to select automatically")
    p_add.add_argument("--edition-id", help="Exact PlayStation Store edition ID to select")
    p_add.add_argument("--target", type=float, help="Target price in INR")
    p_add.add_argument("--allow-free", action="store_true", help="Allow selecting a free-to-play edition")
    p_add.add_argument("-y", "--yes", action="store_true", help="Confirm addition without interactive prompts")

    p_list = subparsers.add_parser("list", help="List all digital tracked games and statuses")

    p_target = subparsers.add_parser("target", help="Set target price for a digital game")
    p_target.add_argument("id", type=int, help="Game ID")
    p_target.add_argument("price", help="Target price in INR")

    p_toggle = subparsers.add_parser("toggle", help="Pause or resume digital game monitoring")
    p_toggle.add_argument("id", type=int, help="Game ID")
    group = p_toggle.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true", help="Enable monitoring")
    group.add_argument("--disable", action="store_true", help="Disable monitoring")

    p_remove = subparsers.add_parser("remove", help="Remove a digital game from active monitoring (preserves history)")
    p_remove.add_argument("id", type=int, help="Game ID")
    p_remove.add_argument("-y", "--yes", action="store_true", help="Confirm removal without prompt")

    p_export = subparsers.add_parser("export", help="Export digital watchlist to JSON file")
    p_export.add_argument("--output", default="watchlist_export.json", help="Output JSON file path")

    p_import = subparsers.add_parser("import", help="Import digital games from JSON file")
    p_import.add_argument("file", help="Path to JSON file")

    # PHYSICAL COMMANDS
    p_retailers = subparsers.add_parser("retailers", help="Show supported Indian retailers and integration statuses")

    p_add_phys = subparsers.add_parser("add-physical", help="Add a physical PS5 game disc to track")
    p_add_phys.add_argument("title", help="Game Title")
    p_add_phys.add_argument("--edition", default="Standard Edition", help="Game Edition")
    p_add_phys.add_argument("--target", type=float, help="Target price in INR")
    p_add_phys.add_argument("--url", help="Initial retailer product URL")
    p_add_phys.add_argument("--sku", help="Product SKU or ASIN")
    p_add_phys.add_argument("--seller", help="Seller name")

    p_add_list = subparsers.add_parser("add-listing", help="Link a retailer product listing to an existing physical game")
    p_add_list.add_argument("game_id", type=int, help="Physical game ID")
    p_add_list.add_argument("url", help="Product URL")
    p_add_list.add_argument("--retailer", help="Retailer code (e.g. amazon_in, flipkart, etc.)")
    p_add_list.add_argument("--sku", help="Product SKU or ASIN")
    p_add_list.add_argument("--seller", help="Seller name")

    p_list_phys = subparsers.add_parser("list-physical", help="List all registered physical game listings")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "target": cmd_target,
        "toggle": cmd_toggle,
        "remove": cmd_remove,
        "export": cmd_export,
        "import": cmd_import,
        "retailers": cmd_retailers,
        "add-physical": cmd_add_physical,
        "add-listing": cmd_add_listing,
        "list-physical": cmd_list_physical,
    }

    exit_code = commands[args.command](args)
    sys.exit(exit_code or 0)


if __name__ == "__main__":
    main()
