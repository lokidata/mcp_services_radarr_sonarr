"""API key authentication for the HTTP transport."""

import hmac
import json

MIN_API_KEY_LENGTH = 16


class ApiKeyMiddleware:
    """ASGI middleware rejecting requests that do not carry the API key.

    The key is read from `Authorization: Bearer <key>` or from `X-API-Key: <key>`
    and compared in constant time. Non-HTTP scopes (lifespan) pass through.
    """

    def __init__(self, app, api_key: str):
        self.app = app
        self._key = api_key.encode("utf-8")

    def _is_authorized(self, scope) -> bool:
        presented = None
        for name, value in scope.get("headers", []):
            if name == b"x-api-key":
                presented = value
                break
            if name == b"authorization" and value[:7].lower() == b"bearer ":
                presented = value[7:].strip()
                break
        return presented is not None and hmac.compare_digest(presented, self._key)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http" or not self._is_authorized(scope):
            if scope["type"] == "http":
                body = json.dumps({"error": "unauthorized"}).encode()
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b'Bearer realm="radarr-sonarr-mcp"'),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
            else:
                await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)
