"""Rate-limited, retrying HTTP client for SEC EDGAR (SPEC §2.2, §5.2).

One ``EdgarClient`` is shared by all workers; its token bucket is what makes the
8 requests/second limit global. The User-Agent (which holds a contact email) is only
ever placed in the request header: never in an exception, a log line or ``repr``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from filinglens.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({"www.sec.gov", "data.sec.gov"})
_RETRY_STATUSES = frozenset({429, 403})
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_UA_MESSAGE = "FL_SEC_USER_AGENT is not set or has no contact email; see .env.example"

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class EdgarConfigError(RuntimeError):
    """User-Agent missing or malformed."""


class EdgarFetchError(RuntimeError):
    """Gave up after retries, or hit a non-retryable status."""

    def __init__(self, url: str, status: int | None, attempts: int, reason: str = "") -> None:
        self.url = url
        self.status = status
        self.attempts = attempts
        detail = f"status {status}" if status is not None else (reason or "transport error")
        super().__init__(f"GET {url} failed after {attempts} attempt(s): {detail}")


@dataclass(slots=True)
class ClientStats:
    requests: int = 0
    retries: int = 0
    bytes: int = 0
    failures: int = 0


class TokenBucket:
    """Tokens refill continuously at ``rate`` per second up to ``capacity``; starts full."""

    def __init__(
        self,
        rate: float,
        capacity: int,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate <= 0 or capacity < 1:
            raise ValueError("rate must be > 0 and capacity >= 1")
        self._rate = rate
        self._capacity = capacity
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(capacity)
        self._last = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(float(self._capacity), self._tokens + elapsed * self._rate)

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                await self._sleep((1.0 - self._tokens) / self._rate)
                self._refill()
            self._tokens = max(0.0, self._tokens - 1.0)


def _validate_user_agent(value: str | None) -> str:
    if value is not None:
        value = value.strip()
    # Needs a contact email and at least one other word (the name).
    if not value or not _EMAIL_RE.search(value) or not _EMAIL_RE.sub("", value).strip():
        raise EdgarConfigError(_UA_MESSAGE)
    return value


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise ValueError("only https://www.sec.gov/ and https://data.sec.gov/ URLs are allowed")


class EdgarClient:
    def __init__(
        self,
        user_agent: str | None = None,
        *,
        rate: float = 8.0,
        max_attempts: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        if user_agent is None:
            user_agent = get_settings().sec_user_agent
        self._user_agent = _validate_user_agent(user_agent)
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._timeout = timeout
        self._transport = transport
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._bucket = TokenBucket(rate, max(1, round(rate)), clock=clock, sleep=sleep)
        self._http: httpx.AsyncClient | None = None
        self._stats = ClientStats()

    def __repr__(self) -> str:
        return f"EdgarClient(max_attempts={self._max_attempts}, requests={self._stats.requests})"

    @property
    def stats(self) -> ClientStats:
        return self._stats

    async def __aenter__(self) -> Self:
        self._http = httpx.AsyncClient(
            transport=self._transport,
            timeout=self._timeout,
            headers={"User-Agent": self._user_agent, "Accept-Encoding": "gzip, deflate"},
            follow_redirects=False,  # a redirect must never carry the User-Agent elsewhere
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def _delay(self, attempt: int, response: httpx.Response | None) -> float:
        delay: float = min(self._max_delay, self._base_delay * 2 ** (attempt - 1))
        delay *= 0.5 + self._rng.random() / 2
        if response is not None:
            try:
                retry_after: float | None = float(response.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = None
            if retry_after is not None:
                delay = min(self._max_delay, max(retry_after, delay))
        return delay

    async def get_bytes(self, url: str) -> bytes:
        _check_url(url)
        if self._http is None:
            raise RuntimeError("EdgarClient must be used as 'async with EdgarClient(...)'")
        attempt = 0
        while True:
            attempt += 1
            await self._bucket.acquire()
            self._stats.requests += 1
            response: httpx.Response | None = None
            reason = ""
            try:
                response = await self._http.get(url)
            except httpx.TransportError as exc:  # includes timeouts
                reason = type(exc).__name__
            status: int | None = None
            if response is not None:
                status = response.status_code
                if 200 <= status < 300:
                    self._stats.bytes += len(response.content)
                    return response.content
                retryable = status in _RETRY_STATUSES or status >= 500
            else:
                retryable = True
            if not retryable or attempt >= self._max_attempts:
                self._stats.failures += 1
                raise EdgarFetchError(url, status, attempt, reason)
            delay = self._delay(attempt, response)
            self._stats.retries += 1
            logger.warning(
                "retrying %s (status %s%s) in %.2fs",
                url,
                status,
                f", {reason}" if reason else "",
                delay,
            )
            await self._sleep(delay)

    async def get_json(self, url: str) -> Any:
        data = await self.get_bytes(url)
        try:
            return json.loads(data)
        except ValueError as exc:
            raise EdgarFetchError(url, None, 1, "invalid JSON") from exc
