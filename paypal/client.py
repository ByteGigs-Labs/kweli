import logging
import threading
import time
import uuid
from typing import Any

import httpx

from api.config import Settings, get_settings
from paypal.auth import AccessToken, fetch_access_token
from paypal.errors import PayPalError, PayPalUnavailable

logger = logging.getLogger("kweli.paypal")

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "DELETE", "PUT"})


def new_request_id() -> str:
    return str(uuid.uuid4())


class PayPalClient:
    """Thin REST client: cached OAuth token, retries with backoff, idempotency keys."""

    def __init__(
        self,
        settings: Settings | None = None,
        http: httpx.Client | None = None,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        sleep=time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self.http = http or httpx.Client(timeout=httpx.Timeout(20, connect=5))
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._token: AccessToken | None = None
        self._lock = threading.Lock()

    def _access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            if force_refresh or self._token is None or not self._token.is_fresh():
                self._token = fetch_access_token(self.settings, self.http)
            return self._token.value

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None and (retry_after := response.headers.get("Retry-After")):
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        return self.backoff_seconds * (2**attempt)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        raw_json: bytes | None = None,
        files: list | None = None,
        params: dict | None = None,
        request_id: str | None = None,
        prefer_representation: bool = False,
    ) -> dict[str, Any]:
        method = method.upper()
        if method == "POST" and request_id is None:
            request_id = new_request_id()
        retry_allowed = method in SAFE_METHODS or request_id is not None
        refreshed = False
        attempt = 0
        while True:
            headers = {
                "Authorization": f"Bearer {self._access_token(force_refresh=refreshed)}",
                "Accept": "application/json",
            }
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            if prefer_representation:
                headers["Prefer"] = "return=representation"
            if raw_json is not None:
                headers["Content-Type"] = "application/json"
            try:
                response = self.http.request(
                    method,
                    f"{self.settings.paypal_base_url}{path}",
                    json=json if raw_json is None and files is None else None,
                    content=raw_json,
                    files=files,
                    params=params,
                    headers=headers,
                )
            except httpx.TransportError as error:
                if retry_allowed and attempt < self.max_retries:
                    self._sleep(self._delay(attempt, None))
                    attempt += 1
                    continue
                raise PayPalUnavailable(0, "NETWORK_ERROR", type(error).__name__) from error

            if response.status_code == 401 and not refreshed:
                refreshed = True
                continue
            if response.status_code in RETRYABLE_STATUSES and retry_allowed:
                if attempt < self.max_retries:
                    logger.info("paypal %s %s -> %s, retrying", method, path, response.status_code)
                    self._sleep(self._delay(attempt, response))
                    attempt += 1
                    continue
                raise _error_from(response, PayPalUnavailable)
            if response.status_code >= 400:
                raise _error_from(response, PayPalError)
            if not response.content:
                return {}
            return response.json()

    def get(self, path: str, **kwargs) -> dict[str, Any]:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict[str, Any]:
        return self.request("POST", path, **kwargs)


def _error_from(response: httpx.Response, kind: type[PayPalError]) -> PayPalError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return kind(
        response.status_code,
        str(body.get("name") or body.get("error") or ""),
        str(body.get("message") or body.get("error_description") or ""),
        str(body.get("debug_id") or response.headers.get("Paypal-Debug-Id", "")),
        body.get("details") if isinstance(body.get("details"), list) else None,
    )
