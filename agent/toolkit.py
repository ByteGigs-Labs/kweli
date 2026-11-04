"""Run PayPal Agent Toolkit tools through Kweli's own PayPal client.

The toolkit (installed with --no-deps, see docs/decisions/0001-agent-toolkit.md) supplies the
tool names, descriptions, argument schemas and request builders. Its handlers call
`client.post/get/put/delete(uri, payload)`; this adapter answers those calls with Kweli's
client, which has timeouts, retries, a cached token, idempotency keys and redacted logs.
"""

from paypal.client import PayPalClient


class ToolkitClientAdapter:
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


def toolkit_specs(methods: set[str]) -> dict[str, dict]:
    from paypal_agent_toolkit.shared.tools import tools

    found = {spec["method"]: spec for spec in tools if spec["method"] in methods}
    missing = methods - set(found)
    if missing:
        raise ValueError(f"Unknown toolkit methods: {sorted(missing)}")
    return found
