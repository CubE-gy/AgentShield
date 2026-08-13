import pytest

from app.rate_limiter import (
    RateLimitExceededError,
    RateLimitUnavailableError,
    enforce_tenant_rate_limit,
)


class FakeRedis:
    def __init__(self):
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


class UnavailableRedis:
    def incr(self, key: str) -> int:
        raise ConnectionError("Redis is unavailable")


def test_first_request_is_allowed_and_starts_window():
    redis_client = FakeRedis()

    enforce_tenant_rate_limit(
        redis_client=redis_client,
        tenant_id="tenant-alpha",
        max_requests=2,
        window_seconds=60,
    )

    assert redis_client.values == {"agentshield:rate-limit:tenant-alpha": 1}
    assert redis_client.expirations == {
        "agentshield:rate-limit:tenant-alpha": 60,
    }


def test_request_over_limit_is_rejected():
    redis_client = FakeRedis()

    enforce_tenant_rate_limit(
        redis_client=redis_client,
        tenant_id="tenant-alpha",
        max_requests=1,
        window_seconds=60,
    )

    with pytest.raises(RateLimitExceededError):
        enforce_tenant_rate_limit(
            redis_client=redis_client,
            tenant_id="tenant-alpha",
            max_requests=1,
            window_seconds=60,
        )


def test_tenants_are_counted_separately():
    redis_client = FakeRedis()

    enforce_tenant_rate_limit(
        redis_client=redis_client,
        tenant_id="tenant-alpha",
        max_requests=1,
        window_seconds=60,
    )
    enforce_tenant_rate_limit(
        redis_client=redis_client,
        tenant_id="tenant-beta",
        max_requests=1,
        window_seconds=60,
    )

    assert redis_client.values == {
        "agentshield:rate-limit:tenant-alpha": 1,
        "agentshield:rate-limit:tenant-beta": 1,
    }


def test_redis_unavailable_rejects_request_safely():
    with pytest.raises(RateLimitUnavailableError):
        enforce_tenant_rate_limit(
            redis_client=UnavailableRedis(),
            tenant_id="tenant-alpha",
            max_requests=1,
            window_seconds=60,
        )
