"""PlayStation Store (en-in) Price Collector using API.SH.

Guarantees:
- Enforces Indian PlayStation Store region: en-in.
- Parses INR display-price text; strictly prohibits USD conversions.
- Concept URL and direct product URL support with edition disambiguation.
- Protects against selecting free-to-play/demo editions when a paid game is intended.
- Never guesses prices or treats unavailable data as ₹0.
"""

import re
from typing import Any, Dict, List, Optional
import requests

import config

API_URL = "https://api.api.sh/playstation/v1/game"


def parse_store_price(value: Any) -> Optional[float]:
    """Parse a display price such as 'Rs 5,999' or 'Free'; strictly avoids currency conversions."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() == "free":
        return 0.0
    # Indian Store display strings can include Rs, ₹, NBSP and commas
    cleaned = re.sub(r"[^\d.]", "", text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def validate_store_url(url: str) -> bool:
    """Validate that the URL belongs to the official Indian PlayStation Store."""
    if not url or not isinstance(url, str):
        return False
    clean = url.strip().lower()
    return "store.playstation.com/en-in/" in clean and ("/concept/" in clean or "/product/" in clean)


def extract_store_id(url: str) -> Optional[str]:
    """Extract concept ID or product ID from a PlayStation Store URL."""
    if not url:
        return None
    clean = url.strip()
    match = re.search(r"/(?:concept|product)/([^/?#]+)", clean)
    return match.group(1) if match else None


class APISHCollector:
    def __init__(self, region: str = "en-in"):
        if not config.APISH_KEY:
            raise RuntimeError("APISH_KEY is missing. Add it to your local .env file.")
        self.region = region.lower()
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": config.APISH_KEY,
            "User-Agent": "PS5DealTracker/2.0"
        })

    def lookup_game(self, store_url: str) -> Dict[str, Any]:
        """Fetch raw game metadata from API.SH for a store URL."""
        if not validate_store_url(store_url):
            raise ValueError(
                f"Invalid or unsupported PlayStation Store URL: '{store_url}'. "
                "Only official Indian PlayStation Store URLs ('store.playstation.com/en-in/...') are permitted."
            )

        response = self.session.get(
            API_URL, params={"id": store_url, "region": self.region}, timeout=45
        )
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or data.get("error"):
            raise ValueError(f"API.SH error response: {data.get('error') or data}")

        returned_region = str(data.get("region", "")).lower()
        if returned_region and returned_region != self.region:
            raise ValueError(f"Region mismatch: requested '{self.region}', received '{returned_region}'")

        return data

    def get_available_editions(self, store_url: str) -> List[Dict[str, Any]]:
        """Retrieve and parse all available editions for a game without saving."""
        data = self.lookup_game(store_url)
        game_name = data.get("name") or "Unknown PS5 Game"
        raw_editions = data.get("editions") or []
        editions = []

        for ed in raw_editions:
            ed_id = str(ed.get("id") or "")
            ed_name = ed.get("name") or game_name
            ed_url = str(ed.get("url") or store_url)
            prices = ed.get("prices") or []

            current_price = None
            original_price = None
            discount_text = None
            sale_ends = None

            for pr in prices:
                currency = str(pr.get("currency") or "").upper()
                if currency and currency != "INR":
                    continue
                curr = parse_store_price(pr.get("price_text"))
                orig = parse_store_price(pr.get("original_price_text"))
                if curr is not None:
                    current_price = curr
                    original_price = orig if orig is not None else curr
                    discount_text = pr.get("discount_text")
                    sale_ends = pr.get("sale_ends")
                    break

            is_free = (current_price == 0.0)
            is_ps5 = any("ps5" in str(p).lower() for p in (ed.get("platforms") or [])) or "ps5" in ed_name.lower() or "ps5" in ed_id.lower()

            editions.append({
                "game_name": game_name,
                "edition_id": ed_id,
                "edition_name": ed_name,
                "current_price": current_price,
                "original_price": original_price,
                "discount_text": discount_text,
                "sale_ends": sale_ends,
                "store_url": ed_url,
                "is_free": is_free,
                "is_ps5": is_ps5,
                "currency": "INR",
            })

        return editions

    def get_game_price(self, game: Dict[str, Any], allow_free: bool = False) -> Dict[str, Any]:
        """Fetch current price for a game entry with full edition disambiguation and free-to-play protection."""
        store_url = game["store_url"]
        requested_id = str(game.get("store_id") or "").strip()
        requested_edition = str(game.get("edition_name") or "").strip().lower()

        available_editions = self.get_available_editions(store_url)
        if not available_editions:
            raise ValueError(f"No editions found for {game.get('name', store_url)}")

        candidates = []
        for ed in available_editions:
            if ed["current_price"] is None:
                continue

            # Exact product ID match
            if requested_id and requested_id.startswith(("EP", "HP", "UP")):
                if requested_id in ed["edition_id"] or requested_id in ed["store_url"]:
                    return ed

            # Exact edition name match if specified
            if requested_edition and requested_edition not in ("standard edition", "standard", ""):
                if requested_edition in ed["edition_name"].lower():
                    candidates.append(ed)
                    continue

            # General candidate
            candidates.append(ed)

        if not candidates:
            candidates = [ed for ed in available_editions if ed["current_price"] is not None]

        if not candidates:
            raise ValueError(
                f"No usable INR display price found for {game.get('name')}. "
                "The tracker will not guess or convert raw numeric prices."
            )

        # Free-to-play protection:
        # If allow_free is False, filter out 0.0 editions when paid editions are available.
        paid_candidates = [c for c in candidates if c["current_price"] > 0]
        if paid_candidates and not allow_free:
            # Check if any paid candidate matches requested edition
            if requested_edition and requested_edition not in ("standard edition", ""):
                matching_paid = [c for c in paid_candidates if requested_edition in c["edition_name"].lower()]
                if matching_paid:
                    return matching_paid[0]
            # Otherwise return lowest paid edition (never selecting free Warzone or demo!)
            return min(paid_candidates, key=lambda item: item["current_price"])

        # If user explicitly allowed free or only free candidates exist
        return min(candidates, key=lambda item: item["current_price"])
