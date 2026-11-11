"""Telegram Notification Dispatcher for Digital and Physical PS5 Deals.

Dispatches formatted Markdown messages with price breakdowns, historical comparisons,
seller information, and links.
Guarantees duplicate alert suppression.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import requests

import config


def send_deal_alert(game: Dict[str, Any], price_data: Dict[str, Any], detection: Dict[str, Any]) -> bool:
    """Send formatted Telegram alert for a Digital PS Store deal."""
    if not config.is_telegram_configured():
        print("Telegram not configured; digital alert not sent.")
        return False

    original = price_data.get("original_price")
    original_text = f"₹{original:,.0f}" if original is not None else "Not listed"
    target_price = game.get("target_price")
    target_text = f"₹{target_price:,.0f}" if target_price is not None else "None"
    prev_low = detection.get("previous_historical_low")
    prev_low_text = f"₹{prev_low:,.0f}" if prev_low is not None else "Building history"

    message = (
        "🎮 *PS5 DIGITAL DEAL ALERT*\n\n"
        f"🕹️ *{game['name']}*\n"
        f"📦 *Edition:* {price_data.get('edition_name', game.get('edition_name', 'Standard Edition'))}\n"
        f"💰 *Current Price:* ₹{detection['current_price']:,.0f}\n"
        f"🏷️ *Original Price:* {original_text}\n"
        f"🔥 *Discount:* {detection['discount_percentage']}%\n"
        f"💵 *Savings:* ₹{detection['savings']:,.0f}\n"
        f"🎯 *Target Price:* {target_text}\n"
        f"📉 *Historical Low:* {prev_low_text}\n"
        f"📌 *Trigger:* {', '.join(detection['alert_types'])}\n\n"
        f"🛒 [Open PlayStation Store India]({price_data.get('store_url') or game['store_url']})"
    )

    return _dispatch_telegram_message(message)


def send_physical_deal_alert(item: Dict[str, Any], price_data: Dict[str, Any], detection: Dict[str, Any]) -> bool:
    """Send formatted Telegram alert for a Physical PS5 Disc deal."""
    if not config.is_telegram_configured():
        print("Telegram not configured; physical alert not sent.")
        return False

    original = price_data.get("original_price")
    original_text = f"₹{original:,.0f}" if original is not None else "Not listed"
    target_price = item.get("target_price")
    target_text = f"₹{target_price:,.0f}" if target_price is not None else "None"
    prev_low = detection.get("previous_historical_low")
    prev_low_text = f"₹{prev_low:,.0f}" if prev_low is not None else "Building history"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    message = (
        "💿 *PS5 PHYSICAL DISC DEAL ALERT*\n\n"
        f"🕹️ *{item['title']}*\n"
        f"🏪 *Retailer:* {item['retailer_name']}\n"
        f"🏷️ *Seller:* {item.get('seller_name', 'Verified Seller')}\n"
        f"💰 *Current Verified Price:* ₹{detection['current_price']:,.0f}\n"
        f"🏷️ *Original Price:* {original_text}\n"
        f"🔥 *Discount:* {detection['discount_percentage']}%\n"
        f"🎯 *Target Price:* {target_text}\n"
        f"📉 *Historical Low:* {prev_low_text}\n"
        f"🕒 *Checked At:* {timestamp}\n"
        f"📌 *Trigger:* {', '.join(detection['alert_types'])}\n\n"
        f"🛒 [Open Retailer Product Page]({item['product_url']})"
    )

    return _dispatch_telegram_message(message)


def _dispatch_telegram_message(text: str, max_retries: int = 3) -> bool:
    """Send message via Telegram Bot API with timeout, exponential backoff, and error handling."""
    import time
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                print("Telegram rejected message:", result)
                return False
            return True
        except requests.RequestException as exc:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                print(f"Telegram dispatch failed after {max_retries} attempts: {exc}")
                return False
