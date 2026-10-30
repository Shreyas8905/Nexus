from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS_VALUE = "max-age=31536000; includeSubDomains"

_STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    # The API only returns JSON / SSE; nothing it serves should ever render or embed.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware:
    """Adds baseline security headers to every HTTP response (pure ASGI, so SSE streams aren't buffered).

    Headers a route already set are left untouched. HSTS is opt-in because it is only meaningful
    (and only safe to pin) once the deployment is served over HTTPS.
    """

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.headers = dict(_STATIC_HEADERS)
        if hsts:
            self.headers["Strict-Transport-Security"] = HSTS_VALUE

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self.headers.items():
                    if name not in headers:
                        headers[name] = value
                # Auth/session responses and chat answers must never be stored by shared caches.
                if "cache-control" not in headers:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)
