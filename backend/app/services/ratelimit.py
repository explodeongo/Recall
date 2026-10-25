"""A small in-memory rate limiter, per client and bucket, over a sliding minute.

Enough for one API process; a multi-process deployment would move this to Postgres or Redis.
"""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def limit(request: Request, bucket: str, per_minute: int, key: str | None = None) -> None:
    who = key or (request.client.host if request.client else "unknown")
    now = time.monotonic()
    hits = _hits[(bucket, who)]
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= per_minute:
        raise HTTPException(429, "Too many requests. Wait a minute and try again.")
    hits.append(now)


def reset() -> None:
    _hits.clear()
