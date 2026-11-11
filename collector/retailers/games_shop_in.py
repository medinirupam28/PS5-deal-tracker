"""Games Shop India (gamesshop.in) Retailer Provider.

Automated collection status: UNAVAILABLE.
Games Shop India does not provide a public developer pricing API.
"""

from typing import Optional

from collector.retailers.base import BaseRetailerProvider, RetailerPriceResult, RetailerStatus


class GamesShopIndiaProvider(BaseRetailerProvider):
    def __init__(self):
        super().__init__(
            code="games_shop_in",
            name="Games Shop India",
            base_url="https://www.gamesshop.in/",
            default_interval_hours=12
        )

    def get_status(self) -> RetailerStatus:
        return RetailerStatus.UNAVAILABLE

    def get_status_message(self) -> str:
        return (
            "Games Shop India (gamesshop.in) does not offer a sanctioned automated price API. "
            "Automated scraping without permission is prohibited."
        )

    def validate_url(self, url: str) -> bool:
        if not url:
            return False
        clean = url.lower()
        return "gamesshop.in" in clean

    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        return RetailerPriceResult(
            success=False,
            status=RetailerStatus.UNAVAILABLE,
            error_message=self.get_status_message()
        )
