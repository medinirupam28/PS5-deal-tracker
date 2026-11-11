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
    target_price: Optional[float] = None,
    minimum_discount: float = 30.0,
    db_instance: Any = None,
    target_deal: Optional[float] = None,
    target_great_deal: Optional[float] = None,
    target_exceptional: Optional[float] = None,
    is_provisional: bool = False,
    target_notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Detect deals for digital PS Store games with multi-tier target support.

    Features:
    - Multi-tier target evaluation: EXCEPTIONAL DEAL > GREAT DEAL > DEAL.
    - Selects the single strongest tier achieved so only 1 alert is sent.
    - Escalation support: alerts when price drops from DEAL into GREAT DEAL or EXCEPTIONAL.
    - Duplicate suppression: suppresses alerts if price has not dropped further or if
      a stronger tier was already alerted at/below current price.
    - Historical lowest price detection.
    - Minimum percentage discount detection.
    """
    active_db = db_instance or default_db
    previous_low = active_db.get_historical_low(game_id)
    discount = 0.0
    if original_price and original_price > current_price:
        discount = round((original_price - current_price) / original_price * 100, 2)

    # 1. Determine highest target tier reached
    highest_tier = None
    target_hit_price = None

    if target_exceptional is not None and current_price <= target_exceptional:
        highest_tier = "EXCEPTIONAL DEAL"
        target_hit_price = target_exceptional
    elif target_great_deal is not None and current_price <= target_great_deal:
        highest_tier = "GREAT DEAL"
        target_hit_price = target_great_deal
    elif target_deal is not None and current_price <= target_deal:
        highest_tier = "DEAL"
        target_hit_price = target_deal
    elif target_price is not None and current_price <= target_price:
        highest_tier = "TARGET PRICE REACHED"
        target_hit_price = target_price

    reasons = []

    # Check tier qualification and deduplication/escalation
    if highest_tier:
        prev_tier_alert = active_db.last_alert_price(game_id, highest_tier)

        # Check stronger tiers: if a stronger tier was already alerted at or below current price, suppress
        stronger_tier_suppressed = False
        if highest_tier == "DEAL":
            prev_great = active_db.last_alert_price(game_id, "GREAT DEAL")
            prev_exc = active_db.last_alert_price(game_id, "EXCEPTIONAL DEAL")
            if (prev_great is not None and prev_great <= current_price) or (prev_exc is not None and prev_exc <= current_price):
                stronger_tier_suppressed = True
        elif highest_tier == "GREAT DEAL":
            prev_exc = active_db.last_alert_price(game_id, "EXCEPTIONAL DEAL")
            if prev_exc is not None and prev_exc <= current_price:
                stronger_tier_suppressed = True

        if not stronger_tier_suppressed:
            if prev_tier_alert is None or current_price < prev_tier_alert:
                reasons.append(highest_tier)

    # Percentage discount detection
    if discount >= minimum_discount:
        disc_reason = f"{minimum_discount}%+ DISCOUNT ({discount}%)"
        prev_disc_alert = active_db.last_alert_price(game_id, disc_reason)
        if prev_disc_alert is None or current_price < prev_disc_alert:
            reasons.append(disc_reason)

    # Historical low detection
    if previous_low is not None and current_price < previous_low:
        prev_low_alert = active_db.last_alert_price(game_id, "NEW HISTORICAL LOW")
        if prev_low_alert is None or current_price < prev_low_alert:
            reasons.append("NEW HISTORICAL LOW")

    if not reasons:
        return None

    return {
        "alert_types": reasons,
        "current_price": current_price,
        "original_price": original_price,
        "discount_percentage": discount,
        "savings": round(max(0, (original_price or current_price) - current_price), 2),
        "previous_historical_low": previous_low,
        "tier": highest_tier,
        "target_hit_price": target_hit_price,
        "target_deal": target_deal,
        "target_great_deal": target_great_deal,
        "target_exceptional": target_exceptional,
        "is_provisional": is_provisional,
        "target_notes": target_notes,
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
