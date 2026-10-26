"""Cache-aside helpers with generation-based invalidation and stampede protection.

* Read path: GET key -> hit: return; miss: take a short per-key lock (SET NX
  PX), load from Postgres, SET with TTL. Concurrent misses wait briefly for
  the lock holder's result instead of all hitting the database (thundering herd).
* Invalidation: problem keys embed a generation number (``cf:cache:problems:gen``).
  Bumping it with INCR atomically orphans every cached list/detail page; the
  orphans age out via TTL. No key scanning, no partial invalidation races.
* Redis failure: the cache fails open and the request is served from Postgres.
* Only public data is cached. Hidden tests are never loaded on these paths.
"""

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import redis

from codeforge_core import keys

from .metrics import CACHE

log = logging.getLogger(__name__)


def generation(r: redis.Redis) -> int:
    try:
        return int(r.get(keys.CACHE_GENERATION) or 0)
    except redis.RedisError:
        return -1


def invalidate_problems(r: redis.Redis) -> int:
    return int(r.incr(keys.CACHE_GENERATION))


def get_or_load(r: redis.Redis, name: str, key: str, ttl: int, loader: Callable[[], Any]) -> tuple[Any, bool]:
    """Returns (value, cache_hit)."""
    try:
        raw = r.get(key)
        if raw is not None:
            CACHE.labels(name, "hit").inc()
            return json.loads(raw), True
        lock_key = f"{key}:lock"
        if not r.set(lock_key, "1", nx=True, px=3000):
            for _ in range(10):  # another request is loading this key; wait up to ~250ms
                time.sleep(0.025)
                raw = r.get(key)
                if raw is not None:
                    CACHE.labels(name, "hit_after_wait").inc()
                    return json.loads(raw), True
    except redis.RedisError as exc:
        CACHE.labels(name, "error").inc()
        log.warning("cache unavailable; reading through", extra={"cache": name, "error": str(exc)})
        return loader(), False

    CACHE.labels(name, "miss").inc()
    value = loader()
    try:
        pipe = r.pipeline()
        pipe.set(key, json.dumps(value, default=str), ex=ttl)
        pipe.delete(f"{key}:lock")
        pipe.execute()
    except redis.RedisError:
        pass
    return value, False
