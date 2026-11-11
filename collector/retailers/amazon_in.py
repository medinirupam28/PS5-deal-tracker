"""Amazon India Retailer Provider.

Requires official Amazon Product Advertising API (PA-API 5.0) credentials.
In accordance with Amazon Conditions of Use and security policy, direct web scraping
and bot-bypass mechanisms are strictly prohibited.
"""

import re
from typing import Optional

import config
from collector.retailers.base import BaseRetailerProvider, RetailerPriceResult, RetailerStatus


class AmazonIndiaProvider(BaseRetailerProvider):
    def __init__(self):
        super().__init__(
            code="amazon_in",
            name="Amazon India",
            base_url="https://www.amazon.in/",
            default_interval_hours=6
        )

    def get_status(self) -> RetailerStatus:
        if config.AMAZON_PAAPI_KEY and config.AMAZON_PAAPI_SECRET and config.AMAZON_ASSOCIATE_TAG:
            return RetailerStatus.ACTIVE
        return RetailerStatus.CREDENTIALS_REQUIRED

    def get_status_message(self) -> str:
        if self.get_status() == RetailerStatus.ACTIVE:
            return "PA-API 5.0 credentials configured."
        return (
            "Amazon PA-API credentials missing. Amazon Terms of Use require official PA-API 5.0 "
            "(AMAZON_PAAPI_KEY, AMAZON_PAAPI_SECRET, AMAZON_ASSOCIATE_TAG). "
            "Automated scraping is not permitted."
        )

    def validate_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "amazon.in" in clean and ("/dp/" in clean or "/gp/product/" in clean or "/d/" in clean)

    def extract_asin(self, url: str) -> Optional[str]:
        if not url:
            return None
        match = re.search(r"/(?:dp|gp/product|d)/([A-Z0-9]{10})", url, re.IGNORECASE)
        return match.group(1).upper() if match else None

    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        status = self.get_status()
        if status != RetailerStatus.ACTIVE:
            return RetailerPriceResult(
                success=False,
                status=status,
                error_message=self.get_status_message()
            )

        asin = sku or self.extract_asin(product_url)
        if not asin:
            return RetailerPriceResult(
                success=False,
                status=status,
                error_message=f"Could not extract ASIN from URL: {product_url}"
            )

        # PA-API 5.0 integration point:
        # In a production environment with approved PA-API credentials, this invokes GetItems API.
        return RetailerPriceResult(
            success=False,
            status=RetailerStatus.CREDENTIALS_REQUIRED,
            error_message="Amazon PA-API endpoint call awaiting active merchant approval."
        )
