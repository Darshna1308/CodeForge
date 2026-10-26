from functools import lru_cache

import redis

from .config import get_settings


@lru_cache
def get_redis(url: str | None = None) -> redis.Redis:
    return redis.Redis.from_url(
        url or get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
        health_check_interval=15,
        retry_on_timeout=True,
    )
