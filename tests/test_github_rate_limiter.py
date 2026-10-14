"""Tests for the Redis-backed GitHub rate limiter."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.github_client import GithubClient, _install_requester_guard
from src.ratelimit.github_limiter import GitHubRateBudgetExhausted, GitHubRateLimiter


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("redis down")

    def incrby(self, key: str, amount: int) -> int:
        self._check()
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    def expire(self, key: str, ttl: int) -> bool:
        self._check()
        self.ttls[key] = ttl
        return True

    def ttl(self, key: str) -> int:
        self._check()
        return self.ttls.get(key, -1)

    def get(self, key: str) -> str | None:
        self._check()
        value = self.store.get(key)
        return str(value) if value is not None else None

    def set(self, key: str, value: int) -> bool:
        self._check()
        self.store[key] = int(value)
        return True


def _limiter(client, **kwargs) -> GitHubRateLimiter:
    return GitHubRateLimiter(client=client, token="tok", **kwargs)


def test_acquire_reserves_and_sets_window_expiry():
    redis = FakeRedis()
    limiter = _limiter(redis, window=3600)
    limiter.acquire()
    assert list(redis.store.values()) == [1]
    assert list(redis.ttls.values()) == [3600]


def test_acquire_raises_when_budget_exhausted():
    redis = FakeRedis()
    limiter = _limiter(redis, budget=2, max_wait=0)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(GitHubRateBudgetExhausted):
        limiter.acquire()


def test_acquire_waits_when_reset_is_imminent(monkeypatch):
    redis = FakeRedis()
    limiter = _limiter(redis, budget=1, max_wait=30)
    limiter.acquire()
    redis.ttls[limiter._key] = 5
    slept: list[int] = []
    monkeypatch.setattr(time, "sleep", slept.append)
    limiter.acquire()
    assert slept == [5]


def test_acquire_skips_rate_limit_endpoint():
    redis = FakeRedis()
    limiter = _limiter(redis)
    limiter.acquire(path="https://api.github.com/rate_limit")
    assert redis.store == {}


def test_acquire_fails_open_and_cools_down():
    redis = FakeRedis()
    limiter = _limiter(redis)
    redis.fail = True
    limiter.acquire()
    redis.fail = False
    limiter.acquire()
    assert redis.store == {}


def test_observe_reconciles_used_upward_and_sets_ttl():
    redis = FakeRedis()
    limiter = _limiter(redis)
    reset = int(time.time()) + 120
    limiter.observe({"x-ratelimit-remaining": "4800", "x-ratelimit-limit": "5000", "x-ratelimit-reset": str(reset)})
    assert redis.store[limiter._key] == 200
    assert 0 < redis.ttls[limiter._key] <= 120


def test_observe_keeps_higher_local_count():
    redis = FakeRedis()
    limiter = _limiter(redis)
    redis.store[limiter._key] = 900
    limiter.observe({"x-ratelimit-remaining": "4800", "x-ratelimit-limit": "5000"})
    assert redis.store[limiter._key] == 900


@pytest.mark.parametrize("headers", [None, {}, {"x-ratelimit-limit": "5000"}])
def test_observe_noop_without_remaining(headers):
    redis = FakeRedis()
    limiter = _limiter(redis)
    limiter.observe(headers)
    assert redis.store == {}


def test_from_env_returns_none_without_config(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    assert GitHubRateLimiter.from_env("tok") is None


def test_from_env_uses_client_and_budget(monkeypatch):
    monkeypatch.setenv("GITHUB_RATE_LIMIT_BUDGET", "1234")
    monkeypatch.setenv("GITHUB_RATE_LIMIT_MAX_WAIT_SECONDS", "7")
    limiter = GitHubRateLimiter.from_env("tok", client=FakeRedis())
    assert limiter is not None
    assert limiter.budget == 1234
    assert limiter.max_wait == 7


def test_from_env_builds_client_from_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://:pw@redis.databases.svc:6379/0")
    monkeypatch.delenv("REDIS_HOST", raising=False)
    limiter = GitHubRateLimiter.from_env("tok")
    assert limiter is not None


def test_from_env_builds_client_from_parts(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.databases.svc")
    monkeypatch.setenv("REDIS_PASSWORD", "pw")
    limiter = GitHubRateLimiter.from_env("tok")
    assert limiter is not None


def test_int_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("GITHUB_RATE_LIMIT_BUDGET", "not-a-number")
    limiter = GitHubRateLimiter.from_env("tok", client=FakeRedis())
    assert limiter is not None
    assert limiter.budget == 4800


def test_observe_fails_open_on_redis_error():
    redis = FakeRedis()
    limiter = _limiter(redis)
    redis.fail = True
    limiter.observe({"x-ratelimit-remaining": "1", "x-ratelimit-limit": "5000"})
    assert redis.store == {}
    redis.fail = False
    limiter.observe({"x-ratelimit-remaining": "1", "x-ratelimit-limit": "5000"})
    assert redis.store == {}



class _FakeRequester:
    def __init__(self) -> None:
        self.called = 0

    def _Requester__requestEncode(
        self, cnx, verb, url, parameters, requestHeaders, input, encode,
        stream=False, follow_302_redirect=False,
    ):
        self.called += 1
        return 200, {"x-ratelimit-remaining": "4900", "x-ratelimit-limit": "5000"}, "{}"


class _FakeGithub:
    def __init__(self, requester: _FakeRequester) -> None:
        self._Github__requester = requester


def test_install_requester_guard_reserves_and_observes():
    redis = FakeRedis()
    limiter = _limiter(redis)
    requester = _FakeRequester()
    _install_requester_guard(_FakeGithub(requester), limiter)  # type: ignore[arg-type]
    status, _headers, _output = getattr(requester, "_Requester__requestEncode")(
        None, "GET", "https://api.github.com/repos/x", None, None, None, None
    )
    assert status == 200
    assert requester.called == 1
    assert redis.store[limiter._key] == 100


def test_update_pr_branch_reserves_and_observes(monkeypatch):
    redis = FakeRedis()
    limiter = _limiter(redis)
    client = GithubClient(token="tok", rate_limiter=limiter)
    acquired: list[str] = []
    observed: list[dict] = []
    monkeypatch.setattr(limiter, "acquire", lambda path="": acquired.append(path))
    monkeypatch.setattr(limiter, "observe", lambda headers: observed.append(headers))

    class _Resp:
        status_code = 422
        text = "nope"
        headers = {"x-ratelimit-remaining": "4900", "x-ratelimit-limit": "5000"}

    monkeypatch.setattr("src.github_client.requests.post", lambda *a, **k: _Resp())
    pr = MagicMock()
    pr.base.repo.full_name = "juninmd/x"

    ok, _msg, _sha = client.update_pr_branch(pr)
    assert ok is False
    assert acquired and observed
    assert client.rate_limiter is limiter
