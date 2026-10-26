"""Token-bucket rate limiting, atomic in Redis via a Lua script.

Each (bucket, subject) pair is a hash {tokens, ts}. The script refills tokens
for the elapsed time using Redis' own clock (TIME), so several API replicas
with skewed clocks still share one consistent bucket, then spends one token or
reports how long until one is available. The whole read-modify-write runs
atomically inside Redis, so concurrent requests cannot both take the last token.
"""

import logging
from dataclasses import dataclass

import redis
from fastapi import Depends, Request

from codeforge_core import keys
from codeforge_core.config import get_settings
from codeforge_core.models import User

from .deps import client_ip, get_current_user, get_r
from .errors import APIError
from .metrics import RATE_LIMITED

log = logging.getLogger(__name__)

TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local per_ms   = tonumber(ARGV[2])
local t        = redis.call('TIME')
local now      = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local state    = redis.call('HMGET', key, 'tokens', 'ts')
local tokens   = tonumber(state[1])
local ts       = tonumber(state[2])
if tokens == nil then tokens = capacity; ts = now end
tokens = math.min(capacity, tokens + math.max(0, now - ts) * per_ms)
local allowed, retry_ms = 0, 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  retry_ms = math.ceil((1 - tokens) / per_ms)
end
redis.call('HSET', key, 'tokens', tostring(tokens), 'ts', now)
redis.call('PEXPIRE', key, math.ceil(capacity / per_ms) + 1000)
return {allowed, math.floor(tokens), retry_ms}
"""


@dataclass(frozen=True)
class Limit:
    capacity: int
    window_s: int

    @classmethod
    def parse(cls, spec: str) -> "Limit":
        cap, window = spec.split("/")
        return cls(int(cap), int(window))


_script_cache: dict[int, object] = {}


def check(r: redis.Redis, bucket: str, subject: str, limit: Limit) -> None:
    if not get_settings().rate_limit_enabled:
        return
    script = _script_cache.get(id(r))
    if script is None:
        script = _script_cache[id(r)] = r.register_script(TOKEN_BUCKET_LUA)
    per_ms = limit.capacity / (limit.window_s * 1000)
    try:
        allowed, remaining, retry_ms = script(keys=[keys.rate_limit(bucket, subject)], args=[limit.capacity, per_ms])
    except redis.RedisError as exc:
        # Fail-open: rate limiting protects capacity, it is not an auth control.
        log.warning("rate limiter unavailable; allowing request", extra={"bucket": bucket, "error": str(exc)})
        return
    if not allowed:
        RATE_LIMITED.labels(bucket).inc()
        retry_s = max(1, -(-int(retry_ms) // 1000))
        raise APIError(
            429, "rate_limited", f"Too many {bucket} requests; retry in {retry_s}s",
            details={"bucket": bucket, "retry_after_s": retry_s},
            headers={"Retry-After": str(retry_s), "X-RateLimit-Limit": str(limit.capacity), "X-RateLimit-Remaining": "0"},
        )


def limit_user(bucket: str, setting_attr: str):
    def dep(user: User = Depends(get_current_user), r: redis.Redis = Depends(get_r)) -> User:
        check(r, bucket, f"user:{user.id}", Limit.parse(getattr(get_settings(), setting_attr)))
        return user

    return dep


def limit_ip(bucket: str, setting_attr: str):
    def dep(request: Request, r: redis.Redis = Depends(get_r)) -> None:
        check(r, bucket, f"ip:{client_ip(request)}", Limit.parse(getattr(get_settings(), setting_attr)))

    return dep
