from starlette.types import ASGIApp, Receive, Scope, Send

from api.config import get_settings
from api.errors import error_body


class BodySizeLimit:
    def __init__(self, app: ASGIApp, upload_prefixes: tuple[str, ...]) -> None:
        self.app = app
        self.upload_prefixes = upload_prefixes

    def _limit(self, path: str) -> int:
        settings = get_settings()
        is_upload = path.startswith(self.upload_prefixes)
        return settings.max_upload_bytes if is_upload else settings.max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and int(declared) > limit:
            await self._reject(send)
            return
        received = 0
        rejected = False

        async def limited_receive():
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message):
            if not rejected:
                await send(message)

        await self.app(scope, limited_receive, guarded_send)
        if rejected:
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        import json

        body = json.dumps(error_body("payload_too_large", "Request body is too large")).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
