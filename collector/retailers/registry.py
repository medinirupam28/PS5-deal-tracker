"""Retailer Registry for PS5 Physical Disc Tracking.

Manages all retailer integrations, status inspections, and price collection dispatching.
"""

from typing import Dict, List, Optional

from collector.retailers.base import BaseRetailerProvider, RetailerPriceResult, RetailerStatus
from collector.retailers.amazon_in import AmazonIndiaProvider
from collector.retailers.flipkart import FlipkartProvider
from collector.retailers.games_the_shop import GamesTheShopProvider
from collector.retailers.games_shop_in import GamesShopIndiaProvider
from collector.retailers.playhq_games import PlayHQGamesProvider


class RetailerRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseRetailerProvider] = {
            "amazon_in": AmazonIndiaProvider(),
            "flipkart": FlipkartProvider(),
            "games_the_shop": GamesTheShopProvider(),
            "games_shop_in": GamesShopIndiaProvider(),
            "playhq": PlayHQGamesProvider(),
        }

    def get_provider(self, code: str) -> Optional[BaseRetailerProvider]:
        return self._providers.get(code)

    def get_all_providers(self) -> List[BaseRetailerProvider]:
        return list(self._providers.values())

    def get_status_summary(self) -> List[Dict[str, str]]:
        return [
            {
                "code": p.code,
                "name": p.name,
                "status": p.get_status().value,
                "check_interval_hours": str(p.check_interval_hours),
                "message": p.get_status_message(),
            }
            for p in self._providers.values()
        ]

    def identify_provider_for_url(self, url: str) -> Optional[BaseRetailerProvider]:
        for p in self._providers.values():
            if p.validate_url(url):
                return p
        return None


# Global registry instance
retailer_registry = RetailerRegistry()
