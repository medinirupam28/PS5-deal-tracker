"""Flipkart Retailer Provider.

Requires official Flipkart Affiliate API or Partner Feed credentials.
Unauthorized automated scraping is prohibited under Flipkart Terms of Service.
"""

from typing import Optional

import config
from collector.retailers.base import BaseRetailerProvider, RetailerPriceResult, RetailerStatus


class FlipkartProvider(BaseRetailerProvider):
    def __init__(self):
        super().__init__(
            code="flipkart",
            name="Flipkart",
            base_url="https://www.flipkart.com/",
            default_interval_hours=6
        )

    def get_status(self) -> RetailerStatus:
        if config.FLIPKART_AFFILIATE_ID and config.FLIPKART_AFFILIATE_TOKEN:
            return RetailerStatus.ACTIVE
        return RetailerStatus.CREDENTIALS_REQUIRED

    def get_status_message(self) -> str:
        if self.get_status() == RetailerStatus.ACTIVE:
            return "Flipkart Affiliate credentials configured."
        return (
            "Flipkart Affiliate credentials missing. Flipkart Terms require partner API credentials "
            "(FLIPKART_AFFILIATE_ID, FLIPKART_AFFILIATE_TOKEN). "
            "Automated scraping is not permitted."
        )

    def validate_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "flipkart.com" in clean and ("/p/" in clean or "pid=" in clean)

    def extract_pid(self, url: str) -> Optional[str]:
        if not url:
            return None
        import re
        match = re.search(r"pid=([A-Z0-9]{16})", url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        # Fallback for /p/itm... format
        match = re.search(r"/p/(itm[a-z0-9]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        status = self.get_status()
        if status != RetailerStatus.ACTIVE:
            return RetailerPriceResult(
                success=False,
                status=status,
                error_message=self.get_status_message()
            )

        pid = sku or self.extract_pid(product_url)
        if not pid:
            return RetailerPriceResult(
                success=False,
                status=status,
                error_message=f"Could not extract Product ID (PID) from URL: {product_url}"
            )

        # Uses Flipkart Affiliate API endpoint:
        # https://affiliate-api.flipkart.net/affiliate/1.0/product.json?id=<pid>
        # with Fk-Affiliate-Id and Fk-Affiliate-Token headers.
        return RetailerPriceResult(
            success=False,
            status=RetailerStatus.CREDENTIALS_REQUIRED,
            error_message="Flipkart Affiliate API call awaiting active partner approval."
        )
