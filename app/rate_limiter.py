from redis import Redis
from redis.exceptions import RedisError


class RateLimitExceededError(Exception):
    """租户在当前时间窗口内的请求次数已达到上限。"""


class RateLimitUnavailableError(Exception):
    """Redis 不可用，无法安全确认请求是否超限。"""


def create_redis_client(redis_url: str) -> Redis:
    """创建 Redis 客户端；实际连接在第一次执行命令时发生。"""

    return Redis.from_url(redis_url, decode_responses=True)


def enforce_tenant_rate_limit(
    *,
    redis_client: Redis,
    tenant_id: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """按租户在固定时间窗口内计数；Redis 故障时拒绝请求。"""

    key = f"agentshield:rate-limit:{tenant_id}"

    try:
        request_count = redis_client.incr(key)
        if request_count == 1:
            redis_client.expire(key, window_seconds)
    except (RedisError, OSError, ConnectionError) as error:
        raise RateLimitUnavailableError("Redis 限流服务不可用") from error

    if request_count > max_requests:
        raise RateLimitExceededError("当前租户请求次数超过限制")
