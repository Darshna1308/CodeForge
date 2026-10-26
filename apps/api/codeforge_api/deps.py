import logging
from collections.abc import Iterator

import jwt
import redis
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from codeforge_core import keys
from codeforge_core.config import get_settings
from codeforge_core.db import get_sessionmaker
from codeforge_core.enums import UserRole
from codeforge_core.models import User
from codeforge_core.redis_client import get_redis

from .errors import APIError
from .security import decode_token

log = logging.getLogger(__name__)


def get_db() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_r() -> redis.Redis:
    return get_redis()


def extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(get_settings().auth_cookie_name)


def _is_revoked(r: redis.Redis, jti: str) -> bool:
    try:
        return bool(r.exists(keys.revoked_token(jti)))
    except redis.RedisError:
        # Fail-open: a Redis outage should not log everyone out. Tokens are
        # short-lived and signed; see docs/SECURITY.md for the trade-off.
        log.warning("revocation check skipped: redis unavailable")
        return False


def get_token_claims(request: Request, r: redis.Redis = Depends(get_r)) -> dict | None:
    token = extract_token(request)
    if not token:
        return None
    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise APIError(401, "token_expired", "Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise APIError(401, "invalid_token", "Invalid authentication token")
    if _is_revoked(r, claims["jti"]):
        raise APIError(401, "token_revoked", "Session has been logged out")
    return claims


def get_optional_user(claims: dict | None = Depends(get_token_claims), db: Session = Depends(get_db)) -> User | None:
    if claims is None:
        return None
    return db.get(User, int(claims["sub"]))


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise APIError(401, "unauthorized", "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise APIError(403, "forbidden", "Administrator role required")
    return user


def client_ip(request: Request) -> str:
    # Behind a trusted reverse proxy you would read X-Forwarded-For here; we do
    # not trust it by default because clients can spoof it.
    return request.client.host if request.client else "unknown"
