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


def get_llm():
    from agent.llm import AnthropicLLM

    return AnthropicLLM.from_settings()


def get_letter_writer():
    from packs.letter import AnthropicLetterWriter

    return AnthropicLetterWriter.from_settings()


def get_response_writer():
    from defender.response import AnthropicResponseWriter

    return AnthropicResponseWriter.from_settings()
