"""
Route-level rate limiting for unauthenticated endpoints.

IMPORTANT — this is a first line of defence, not a complete one.

The window lives in process memory. On a serverless platform each invocation
may run in a fresh instance, and concurrent invocations do not share state, so
a determined attacker spreading requests across instances defeats it. It still
does real work: it stops a naive burst from one address against one warm
instance, which is what credential-stuffing and signup-spam scripts actually
look like by default, and it costs nothing per request.

The durable fix is a shared counter — Postgres, as the feedback intake does,
or an edge rate limiter in front of the app. Feedback could use the database
because it already writes a row per submission; auth attempts have no such
row, and adding a write per login attempt would hand an attacker a cheap way
to generate database load. Hence memory here, with the limitation stated.

Addresses are HMAC'd with the same helper the feedback intake uses, so no raw
IP is ever held in memory or logged.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from .config import Settings
from .feedback import hash_ip

# hashed key -> timestamps of recent hits, oldest first.
_HITS: dict[str, deque[float]] = defaultdict(deque)

# Stop unbounded growth if a lot of distinct addresses arrive. Well above any
# legitimate concurrent-client count for these routes; the eviction is crude
# because the whole structure is best-effort by design.
_MAX_KEYS = 10_000


def _prune(hits: deque[float], cutoff: float) -> None:
    while hits and hits[0] < cutoff:
        hits.popleft()


def check_rate_limit(
    request: Request,
    settings: Settings,
    *,
    bucket: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """
    Raise 429 if this address has exceeded `limit` hits in the window.

    `bucket` namespaces the counter so, say, login and register do not consume
    each other's allowance.
    """
    client_ip = request.client.host if request.client else None
    key = f"{bucket}:{hash_ip(client_ip, settings) or 'unknown'}"

    now = time.monotonic()
    cutoff = now - window_seconds

    if len(_HITS) > _MAX_KEYS:
        _HITS.clear()

    hits = _HITS[key]
    _prune(hits, cutoff)

    if len(hits) >= limit:
        retry_after = max(1, int(window_seconds - (now - hits[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many attempts. Try again in {retry_after} seconds."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    hits.append(now)


def reset() -> None:
    """Clear all windows. For tests."""
    _HITS.clear()
