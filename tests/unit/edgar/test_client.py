from __future__ import annotations

import asyncio
import random

import httpx
import pytest
import respx

from filinglens.edgar.client import EdgarClient, EdgarConfigError, EdgarFetchError, TokenBucket

UA = "Test Name test@example.com"
URL = "https://data.sec.gov/submissions/CIK0000320193.json"
BAD_URL = "https://data.sec.gov/submissions/CIK0000000001.json"


class FakeTime:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


@pytest.fixture
def ft() -> FakeTime:
    return FakeTime()


def make_client(ft: FakeTime, **kw: object) -> EdgarClient:
    return EdgarClient(UA, clock=ft.clock, sleep=ft.sleep, rng=random.Random(1), **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [None, "", "NoEmail", "a@b.c"])
def test_user_agent_rejected(bad: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FL_SEC_USER_AGENT", raising=False)
    if bad is None:
        monkeypatch.setattr(
            "filinglens.edgar.client.get_settings",
            lambda: type("S", (), {"sec_user_agent": None})(),
        )
    with pytest.raises(EdgarConfigError) as info:
        EdgarClient(bad)
    assert "FL_SEC_USER_AGENT" in str(info.value)
    if bad:
        assert bad not in str(info.value)


@respx.mock
async def test_user_agent_sent_and_never_leaked(ft: FakeTime) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"ok"))
    client = make_client(ft)
    async with client:
        assert await client.get_bytes(URL) == b"ok"
    request = route.calls.last.request
    assert request.headers["User-Agent"] == UA
    assert request.headers["Accept-Encoding"] == "gzip, deflate"
    assert "test@example.com" not in repr(client)
    assert "test@example.com" not in str(client.stats)


@respx.mock
async def test_host_check(ft: FakeTime) -> None:
    route = respx.route().mock(return_value=httpx.Response(200))
    async with make_client(ft) as client:
        for bad in ["https://example.com/x", "http://www.sec.gov/x", "https://sec.gov.evil.com/x"]:
            with pytest.raises(ValueError):
                await client.get_bytes(bad)
    assert route.call_count == 0


async def test_token_bucket_alone() -> None:
    ft = FakeTime()
    bucket = TokenBucket(8.0, 8, clock=ft.clock, sleep=ft.sleep)
    for _ in range(8):
        await bucket.acquire()
    assert ft.sleeps == []
    await bucket.acquire()
    assert ft.sleeps == [pytest.approx(0.125)]


@respx.mock
async def test_rate_limit_sequential(ft: FakeTime) -> None:
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(ft.now)
        return httpx.Response(200, content=b"x")

    respx.get(URL).mock(side_effect=handler)
    start = ft.now
    async with make_client(ft) as client:
        for _ in range(20):
            await client.get_bytes(URL)
    assert ft.now - start >= 1.5 - 1e-9
    assert len(times) == 20
    for t in times:
        assert sum(1 for u in times if t <= u < t + 1.0) <= 16


@respx.mock
async def test_rate_limit_concurrent(ft: FakeTime) -> None:
    times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(ft.now)
        return httpx.Response(200, content=b"x")

    respx.get(URL).mock(side_effect=handler)
    start = ft.now
    async with make_client(ft) as client:
        await asyncio.gather(*(client.get_bytes(URL) for _ in range(20)))
    assert ft.now - start >= 1.5 - 1e-9
    assert len(times) == 20
    for t in times:
        assert sum(1 for u in times if t <= u < t + 1.0) <= 16


@pytest.mark.parametrize("status", [429, 503, 403])
@respx.mock
async def test_backoff(status: int, ft: FakeTime) -> None:
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(status),
            httpx.Response(status),
            httpx.Response(200, content=b"ok"),
        ]
    )
    async with make_client(ft) as client:
        assert await client.get_bytes(URL) == b"ok"
        assert client.stats.retries == 2
    assert route.call_count == 3
    assert len(ft.sleeps) == 2
    assert 0.5 <= ft.sleeps[0] <= 1.0
    assert 1.0 <= ft.sleeps[1] <= 2.0


@respx.mock
async def test_retry_after(ft: FakeTime) -> None:
    respx.get(URL).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)]
    )
    async with make_client(ft) as client:
        await client.get_bytes(URL)
    assert ft.sleeps == [7.0]


@respx.mock
async def test_gives_up(ft: FakeTime) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(500))
    async with make_client(ft) as client:
        with pytest.raises(EdgarFetchError) as info:
            await client.get_bytes(URL)
        assert client.stats.failures == 1
    assert info.value.attempts == 5
    assert info.value.status == 500
    assert route.call_count == 5
    assert len(ft.sleeps) == 4


@respx.mock
async def test_no_retry_on_404(ft: FakeTime) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    async with make_client(ft) as client:
        with pytest.raises(EdgarFetchError) as info:
            await client.get_bytes(URL)
    assert info.value.status == 404
    assert info.value.attempts == 1
    assert route.call_count == 1
    assert ft.sleeps == []


@respx.mock
async def test_timeout_then_success(ft: FakeTime) -> None:
    route = respx.get(URL).mock(
        side_effect=[
            httpx.ReadTimeout("t"),
            httpx.ReadTimeout("t"),
            httpx.Response(200, content=b"ok"),
        ]
    )
    async with make_client(ft) as client:
        assert await client.get_bytes(URL) == b"ok"
    assert route.call_count == 3


@respx.mock
async def test_retries_pass_through_bucket(ft: FakeTime) -> None:
    # Every attempt takes a token: 10 attempts with a bucket of 8 must make the bucket sleep.
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"x"))
    respx.get(BAD_URL).mock(return_value=httpx.Response(500))
    async with make_client(ft, max_attempts=3, base_delay=0.0) as client:
        with pytest.raises(EdgarFetchError):
            await client.get_bytes(BAD_URL)
        for _ in range(6):
            await client.get_bytes(URL)
    # 3 failing attempts + 6 = 9 requests > capacity 8, so at least one bucket sleep of 0.125.
    assert any(s == pytest.approx(0.125) for s in ft.sleeps)


@respx.mock
async def test_get_json(ft: FakeTime) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"cik": 320193}))
    async with make_client(ft) as client:
        assert await client.get_json(URL) == {"cik": 320193}


@pytest.mark.parametrize("status", [301, 302, 304])
@respx.mock
async def test_redirect_is_an_error(status: int, ft: FakeTime) -> None:
    route = respx.get(URL).mock(
        return_value=httpx.Response(
            status, content=b"moved", headers={"Location": "https://www.sec.gov/other"}
        )
    )
    other = respx.get("https://www.sec.gov/other").mock(return_value=httpx.Response(200))
    async with make_client(ft) as client:
        with pytest.raises(EdgarFetchError) as info:
            await client.get_bytes(URL)
        assert client.stats.failures == 1
    assert info.value.status == status
    assert info.value.attempts == 1
    assert route.call_count == 1
    assert other.call_count == 0
    assert ft.sleeps == []
