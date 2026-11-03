import httpx

from api.config import Settings
from paypal.client import PayPalClient

TOKEN_BODY = {"access_token": "A21AAfaketoken", "scope": "", "app_id": "APP-1", "expires_in": 3600}


def sandbox_settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://u:p@h/db",
        "paypal_client_id": "client-id",
        "paypal_client_secret": "client-secret",
    } | overrides
    return Settings(_env_file=None, **values)


class FakePayPal:
    """Routes requests to queued responses and records every request."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.routes: dict[tuple[str, str], list] = {}
        self.token_calls = 0

    def queue(self, method: str, path: str, *responses) -> None:
        self.routes.setdefault((method, path), []).extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            self.token_calls += 1
            return httpx.Response(200, json=TOKEN_BODY)
        self.requests.append(request)
        queued = self.routes.get((request.method, request.url.path))
        if not queued:
            return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})
        response = queued.pop(0) if len(queued) > 1 else queued[0]
        if isinstance(response, Exception):
            raise response
        return response

    def client(self, **kwargs) -> PayPalClient:
        http = httpx.Client(transport=httpx.MockTransport(self.handler))
        return PayPalClient(sandbox_settings(), http, sleep=lambda _: None, **kwargs)
