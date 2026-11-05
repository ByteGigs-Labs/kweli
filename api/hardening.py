"""Defence in depth for every API response and every state-changing request.

- Security headers on all responses. API JSON is never cached, and never framed or sniffed.
- An Origin check on POST, PUT, PATCH and DELETE. The session cookie is already
  SameSite=Strict; this also refuses a cross-site request outright if a browser ever sends one.
  Requests without an Origin header (PayPal webhooks, curl, tests) aren't browsers on another
  site, so they pass to the normal authentication.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from api.config import get_settings
from api.errors import error_body

UNSAFE = frozenset({b"POST", b"PUT", b"PATCH", b"DELETE"})
HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-resource-policy", b"same-site"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
]


def allowed_origins() -> set[str]:
    settings = get_settings()
    origins = {origin.rstrip("/") for origin in settings.cors_origins}
    origins.add(settings.public_web_url.rstrip("/"))
    return origins


class Hardening:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope["headers"])
        origin = headers.get(b"origin")
        if scope["method"].encode() in UNSAFE and origin is not None:
            if origin.decode("latin-1").rstrip("/") not in allowed_origins():
                await self._refuse(send)
                return
        secure = get_settings().cookie_secure
        is_api = scope["path"].startswith("/v1/")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(n, v) for n, v in HEADERS if n not in existing]
                if is_api and b"cache-control" not in existing:
                    extra.append((b"cache-control", b"no-store"))
                if secure:
                    extra.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                message["headers"] = [*message.get("headers", []), *extra]
            await send(message)

        await self.app(scope, receive, send_with_headers)

    @staticmethod
    async def _refuse(send: Send) -> None:
        import json

        body = json.dumps(error_body("bad_origin", "This request came from another site")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    *HEADERS,
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
