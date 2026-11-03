class PayPalError(RuntimeError):
    """An error response from PayPal, without credentials or request bodies."""

    def __init__(
        self,
        status: int,
        name: str = "",
        message: str = "",
        debug_id: str = "",
        details: list | None = None,
    ) -> None:
        self.status = status
        self.name = name
        self.message = message
        self.debug_id = debug_id
        self.details = details or []
        super().__init__(f"PayPal {status} {name}: {message} (debug_id={debug_id})".strip())

    @property
    def issues(self) -> list[str]:
        return [detail.get("issue", "") for detail in self.details if isinstance(detail, dict)]


class PayPalUnavailable(PayPalError):
    """PayPal could not be reached or kept failing after retries."""
