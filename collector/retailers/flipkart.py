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

    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        status = self.get_status()
        if status != RetailerStatus.ACTIVE:
            return RetailerPriceResult(
                success=False,
                status=status,
                error_message=self.get_status_message()
            )

        return RetailerPriceResult(
            success=False,
            status=RetailerStatus.CREDENTIALS_REQUIRED,
            error_message="Flipkart Affiliate endpoint call awaiting active partner approval."
        )
