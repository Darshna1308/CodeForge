"""Per-submission lifecycle events.

Each submission gets a small Redis Stream. Workers append events; the SSE
gateway tails it with XREAD BLOCK. Using a stream (rather than PUB/SUB) means
a client that connects late or reconnects after a network blip can replay
from its Last-Event-ID instead of silently missing events.
"""

import json
import logging
import time
from typing import Any

import redis

from . import keys

log = logging.getLogger(__name__)

EVENT_TTL_SECONDS = 3600
EVENT_MAXLEN = 500


def publish(r: redis.Redis, submission_id: int, event_type: str, **data: Any) -> str | None:
    """Best-effort publish. The database remains authoritative if Redis is down."""
    payload = {"type": event_type, "ts": int(time.time() * 1000), **data}
    key = keys.submission_events(submission_id)
    try:
        pipe = r.pipeline()
        pipe.xadd(key, {"data": json.dumps(payload)}, maxlen=EVENT_MAXLEN, approximate=True)
        pipe.expire(key, EVENT_TTL_SECONDS)
        res = pipe.execute()
        return res[0]
    except redis.RedisError as exc:
        log.warning("event publish failed", extra={"event_type": event_type, "error": str(exc)})
        return None


def decode(fields: dict[str, str]) -> dict[str, Any]:
    return json.loads(fields["data"])
