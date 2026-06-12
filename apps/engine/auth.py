"""Shared API-key auth + a tiny in-process rate limiter for the engine.

Auth is OPT-IN: if the ``API_KEY`` env var is unset, ``require_api_key`` is a
no-op (preserves the original open behaviour for local dev). When set, callers
must send ``x-api-key: <key>``.
"""
import os
import time
from collections import deque

from fastapi import Header, HTTPException, Request, status


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    required = os.getenv("API_KEY")
    if not required:
        return
    if x_api_key != required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


class RateLimiter:
    """Fixed-window-ish sliding limiter keyed by client IP. Protects the paid
    LLM endpoints from runaway/abuse. Per-process only (single worker)."""

    def __init__(self, limit: int, window_s: int) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque] = {}

    def __call__(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        dq = self._hits.setdefault(ip, deque())
        while dq and now - dq[0] > self.window_s:
            dq.popleft()
        if len(dq) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded — slow down",
            )
        dq.append(now)


# LLM/analysis endpoints are expensive (paid). Default: 20 requests / 5 min / IP.
llm_rate_limiter = RateLimiter(
    limit=int(os.getenv("LLM_RATE_LIMIT", "20")),
    window_s=int(os.getenv("LLM_RATE_WINDOW_S", "300")),
)
