from decimal import Decimal

ZERO_DECIMAL_CURRENCIES = frozenset({"HUF", "JPY", "TWD"})


def _exponent(currency: str) -> int:
    return 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2


def to_paypal_value(amount_minor: int, currency: str) -> str:
    if amount_minor < 0:
        raise ValueError("Amounts must not be negative")
    exponent = _exponent(currency)
    if exponent == 0:
        return str(amount_minor)
    return f"{Decimal(amount_minor).scaleb(-exponent):.{exponent}f}"


def from_paypal_value(value: str, currency: str) -> int:
    exponent = _exponent(currency)
    scaled = Decimal(value).scaleb(exponent)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{value} has more decimals than {currency} allows")
    return int(scaled)


def money(amount_minor: int, currency: str) -> dict[str, str]:
    return {"currency_code": currency.upper(), "value": to_paypal_value(amount_minor, currency)}
