from functools import lru_cache

from api.services.extract import AnthropicExtractor, Extractor
from paypal.client import PayPalClient


@lru_cache
def _paypal() -> PayPalClient:
    return PayPalClient()


def get_paypal() -> PayPalClient:
    return _paypal()


def get_extractor() -> Extractor | None:
    return AnthropicExtractor.from_settings()
