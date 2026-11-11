"""Base Retailer Provider interface for Physical PS5 Disc Price Tracker.

Enforces strict compliance:
- Standardized status flags (ACTIVE, CREDENTIALS_REQUIRED, UNAVAILABLE).
- Prohibits mock prices and unauthorized scraping.
- Enforces INR currency and stock status checks.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RetailerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CREDENTIALS_REQUIRED = "CREDENTIALS_REQUIRED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class RetailerPriceResult:
    success: bool
    status: RetailerStatus
    price: Optional[float] = None
    original_price: Optional[float] = None
    discount_percentage: float = 0.0
    in_stock: bool = False
    seller_name: Optional[str] = None
    product_title: Optional[str] = None
    currency: str = "INR"
    error_message: Optional[str] = None


class BaseRetailerProvider(ABC):
    def __init__(self, code: str, name: str, base_url: str, default_interval_hours: int = 12):
        self.code = code
        self.name = name
        self.base_url = base_url
        self.check_interval_hours = default_interval_hours

    @abstractmethod
    def get_status(self) -> RetailerStatus:
        """Return the operational status of this provider."""
        pass

    @abstractmethod
    def get_status_message(self) -> str:
        """Return a human-readable description of current status or missing requirements."""
        pass

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """Validate whether a product URL belongs to this retailer."""
        pass

    @abstractmethod
    def fetch_price(self, product_url: str, sku: Optional[str] = None) -> RetailerPriceResult:
        """Fetch the live price for a product URL/SKU using permitted integration."""
        pass
