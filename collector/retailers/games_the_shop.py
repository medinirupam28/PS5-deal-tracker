"""Games The Shop Retailer Provider.

Automated collection status: UNAVAILABLE.
Games The Shop does not publish a sanctioned public pricing API,
and robots.txt disallows automated API interactions (/api/).
"""

from typing import Optional

from collector.retailers.base import BaseRetailerProvider, RetailerPriceResult, RetailerStatus


class GamesTheShopProvider(BaseRetailerProvider):
    def __init__(self):
        super().__init__(
            code="games_the_shop",
            name="Games The Shop",
            base_url="https://www.gamestheshop.com/",
            default_interval_hours=12
        )

    def get_status(self) -> RetailerStatus:
        return RetailerStatus.UNAVAILABLE

    def get_status_message(self) -> str:
        return (
            "Games The Shop does not offer a sanctioned public automated price API. "
            "Robots.txt explicitly disallows /api/ access. Automated scraping is prohibited."
        )

    def validate_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "gamestheshop.com" in clean

    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        return RetailerPriceResult(
            success=False,
            status=RetailerStatus.UNAVAILABLE,
            error_message=self.get_status_message()
        )
