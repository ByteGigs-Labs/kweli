"""PayPal Agent Toolkit tools for LangChain, executed through Kweli's own PayPal client.

We keep the toolkit's tool names, descriptions, argument schemas and request builders, but
send the HTTP calls through `paypal.client.PayPalClient` (timeouts, retries, cached token,
idempotency keys, redacted logs) instead of the toolkit's own client. See
docs/decisions/0001-agent-toolkit.md.
"""

from collections.abc import Iterable
from functools import partial

from langchain_core.tools import StructuredTool

from paypal.client import PayPalClient
from paypal.errors import PayPalError


class ToolkitClientAdapter:
    """The interface the toolkit's handlers call, backed by PayPalClient."""

    def __init__(self, client: PayPalClient) -> None:
        self.client = client

    def post(self, uri: str, payload: dict | None = None) -> dict:
        return self.client.post(uri, json=payload)

    def get(self, uri: str) -> dict:
        return self.client.get(uri)

    def put(self, uri: str, payload: dict | None = None, headers: dict | None = None) -> dict:
        return self.client.request("PUT", uri, json=payload)

    def delete(self, uri: str) -> dict:
        return self.client.request("DELETE", uri)


def _execute(handler, adapter: ToolkitClientAdapter, method: str, **params) -> str:
    try:
        return handler(adapter, params)
    except PayPalError as error:
        issues = ", ".join(error.issues) or error.message or "no details"
        return f"PayPal rejected {method}: {error.name or error.status} ({issues})"
    except ValueError as error:
        return f"Invalid arguments for {method}: {str(error)[:300]}"


def paypal_tools(
    allowed_methods: Iterable[str],
    client: PayPalClient | None = None,
    specs: list[dict] | None = None,
) -> list[StructuredTool]:
    if specs is None:
        from paypal_agent_toolkit.shared.tools import tools as specs
    allowed = set(allowed_methods)
    adapter = ToolkitClientAdapter(client or PayPalClient())
    found = [spec for spec in specs if spec["method"] in allowed]
    missing = allowed - {spec["method"] for spec in found}
    if missing:
        raise ValueError(f"Unknown toolkit methods: {sorted(missing)}")
    return [
        StructuredTool(
            name=spec["method"],
            description=spec["description"],
            args_schema=spec["args_schema"],
            func=partial(_execute, spec["execute"], adapter, spec["method"]),
        )
        for spec in found
    ]
