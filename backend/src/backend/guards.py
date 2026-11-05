"""Request guards: body size, security headers and rate limits. Uvicorn and FastAPI have none of their own."""

import threading
import time

from fastapi import HTTPException, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.errors import error_response

MAX_UPLOAD = 10 * 1024 * 1024
MAX_JSON = 64 * 1024  # a 10 000 character message is at most 40 kB


class BodyLimit:
    """Stops reading a body at its limit. FastAPI reads whole bodies into memory before it validates them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD if scope["path"].endswith("/documents") else MAX_JSON
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        if not declared.isdigit() or int(declared) > limit:
            return await error_response(413, "Request too large")(scope, receive, send)
        received = 0

        async def limited() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:  # a chunked body has no Content-Length
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="Request too large")
            return message

        await self.app(scope, limited, send)


# The API only answers JSON and PDFs: nothing may run, be framed or be cached (answers hold personal data).
HEADERS = [
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
]


class SecurityHeaders:
    """Pure ASGI, unlike @app.middleware, so streamed replies and client disconnects work as before."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                names = {name for name, _ in message["headers"]}
                message["headers"] = [*message["headers"], *((n, v) for n, v in HEADERS if n not in names)]
            await send(message)

        await self.app(scope, receive, with_headers if scope["type"] == "http" else send)


class Limit:
    """At most `count` hits per key in a sliding window of `window` seconds.

    shortcut: in memory and per process, lost on restart; with several workers move it to Redis or the proxy.
    """

    instances: list["Limit"] = []

    def __init__(self, count: int, window: int) -> None:
        self.count, self.window = count, window
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()  # sync endpoints run in a thread pool
        Limit.instances.append(self)

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self.hits.pop(key, []) if now - t < self.window]
        if hits:
            self.hits[key] = hits
        return hits

    def check(self, key: str) -> None:
        """Raises 429 if the key has no hits left. Does not count one."""
        with self.lock:
            if len(self._recent(key, time.monotonic())) >= self.count:
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests",
                    headers={"Retry-After": str(self.window)},
                )

    def add(self, key: str) -> None:
        with self.lock:
            now = time.monotonic()
            self.hits[key] = [*self._recent(key, now), now]

    def take(self, key: str) -> None:
        self.check(key)
        self.add(key)


LOGIN_FAILURES = Limit(5, 15 * 60)  # per email: online guessing
PASSWORD_FAILURES = Limit(5, 15 * 60)  # per user: the password checks of a logged-in session
REGISTRATIONS = Limit(20, 60 * 60)  # per client address. Behind the dev proxy all users share one.
TURNS = Limit(60, 60 * 60)  # per user: each turn can make up to five LLM calls
UPLOADS = Limit(10, 60 * 60)  # per user: each letter is one large LLM call


def reset_limits() -> None:
    for limit in Limit.instances:
        limit.hits.clear()
