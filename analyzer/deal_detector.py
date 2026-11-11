"""Deal detection and analysis engine for Digital and Physical PS5 games.

Features:
- Target price reached detection.
- Percentage discount detection.
- Historical lowest price detection (requiring existing baseline).
- Alert deduplication: suppresses duplicate alerts when prices have not dropped further.
"""

from typing import Any, Dict, List, Optional
from database.db import db as default_db


def detect_deal(
    game_id: int,
    current_price: float,
    original_price: Optional[float],
    target_price: Optional[float],
    minimum_discount: float = 30.0,
    db_instance: Any = None
) -> Optional[Dict[str, Any]]:
    """Detect deals for digital PS Store games."""
    active_db = db_instance or default_db
    previous_low = active_db.get_historical_low(game_id)
    discount = 0.0
    if original_price and original_price > current_price:
        discount = round((original_price - current_price) / original_price * 100, 2)

    reasons = []
    if target_price is not None and current_price <= target_price:
        reasons.append("TARGET PRICE REACHED")
    if discount >= minimum_discount:
        reasons.append(f"{minimum_discount}%+ DISCOUNT ({discount}%)")
    # Baseline must exist before a new historical low can be recognized
    if previous_low is not None and current_price < previous_low:
        reasons.append("NEW HISTORICAL LOW")

    new_reasons = []
    for reason in reasons:
        prev_alert = active_db.last_alert_price(game_id, reason)
        if prev_alert is None or current_price < prev_alert:
            new_reasons.append(reason)

    if not new_reasons:
        return None

    return {
        "alert_types": new_reasons,
        "current_price": current_price,
        "original_price": original_price,
        "discount_percentage": discount,
        "savings": round(max(0, (original_price or current_price) - current_price), 2),
        "previous_historical_low": previous_low,
    }


def detect_physical_deal(
    physical_game_id: int,
    listing_id: int,
    current_price: float,
    original_price: Optional[float],
    target_price: Optional[float],
    minimum_discount: float = 20.0,
    db_instance: Any = None
) -> Optional[Dict[str, Any]]:
    """Detect deals for physical PS5 game discs across retailers."""
    active_db = db_instance or default_db
    previous_low = active_db.get_physical_historical_low(physical_game_id)
    discount = 0.0
    if original_price and original_price > current_price:
        discount = round((original_price - current_price) / original_price * 100, 2)

    reasons = []
    if target_price is not None and current_price <= target_price:
        reasons.append("TARGET PRICE REACHED")
    if discount >= minimum_discount:
        reasons.append(f"{minimum_discount}%+ DISCOUNT ({discount}%)")
    if previous_low is not None and current_price < previous_low:
        reasons.append("NEW HISTORICAL LOW")

    new_reasons = []
    for reason in reasons:
        prev_alert = active_db.last_physical_alert_price(listing_id, reason)
        if prev_alert is None or current_price < prev_alert:
            new_reasons.append(reason)

    if not new_reasons:
        return None

    return {
        "alert_types": new_reasons,
        "current_price": current_price,
        "original_price": original_price,
        "discount_percentage": discount,
        "savings": round(max(0, (original_price or current_price) - current_price), 2),
        "previous_historical_low": previous_low,
    }
