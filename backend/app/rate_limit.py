"""Shared rate limiter for the API.

Keyed by client IP (honoring a single `X-Forwarded-For` hop, since the app
runs behind a reverse proxy/CDN in production). In-memory storage is fine for
a single-process deployment; if this ever runs multi-process/multi-instance,
point `storage_uri` at a shared Redis instance instead so limits are enforced
consistently across workers.
"""

from fastapi import Request
from slowapi import Limiter


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=client_ip, default_limits=["200/minute"])
