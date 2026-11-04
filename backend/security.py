"""Passwords, tokens, rate limits, request checks and response headers."""
from __future__ import annotations

import hashlib
import re
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_hasher = PasswordHasher()
# Verified against when the Email ID is unknown, so timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")
PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{10,128}$")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only this hash is stored, so a stolen database holds no usable session."""
    return hashlib.sha256(token.encode()).hexdigest()


class SlidingWindowLimiter:
    """Per-key request counter held in memory. One process only; see docs/10_SECURITY.md."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        if len(self._hits) > 50_000:
            self._hits = defaultdict(deque, {key: hits})
        return True


PROXY_HEADERS = ("cf-connecting-ip", "x-forwarded-for")


def client_ip(request: Request) -> str:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and runtime.settings.trust_proxy:
        for header in PROXY_HEADERS:
            value = request.headers.get(header)
            if value:
                return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def came_through_proxy(request: Request) -> bool:
    return any(request.headers.get(header) for header in PROXY_HEADERS)


def origin_allowed(origin: str | None, public_origin: str, host: str | None) -> bool:
    """Same-origin only. A missing Origin is a non-browser client, which holds no cookie to abuse."""
    if not origin:
        return True
    parsed = urlparse(origin)
    public = urlparse(public_origin)
    if (parsed.scheme, parsed.netloc) == (public.scheme, public.netloc):
        return True
    return bool(host) and parsed.netloc == host


CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self' ws: wss:; "
    "media-src 'self' blob:; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Adds headers to every response, limits request rate and refuses cross-site writes."""

    def __init__(self, app, limiter: SlidingWindowLimiter, public_origin: str, production: bool) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._public_origin = public_origin
        self._production = production

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path.startswith("/api/"):
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not origin_allowed(
                request.headers.get("origin"), self._public_origin, request.headers.get("host")
            ):
                return JSONResponse({"detail": "This request came from another site."}, status_code=403)
            if not self._limiter.allow(client_ip(request)):
                return JSONResponse(
                    {"detail": "Too many requests. Please wait a minute and try again."},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
        response.headers["Content-Security-Policy"] = CSP
        if self._production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
