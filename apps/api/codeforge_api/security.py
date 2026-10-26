"""Password hashing (Argon2id) and JWT session tokens."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from codeforge_core.config import get_settings

_hasher = PasswordHasher()  # argon2id, library defaults (memory-hard)

# Verifying against a dummy hash when the user does not exist keeps login
# timing roughly constant, so response time does not reveal valid usernames.
_DUMMY_HASH = _hasher.hash("codeforge-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_token(user_id: int, username: str, role: str) -> tuple[str, dict]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "usr": username,
        "role": role,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_ttl_minutes)).timestamp()),
        "iss": "codeforge",
    }
    return jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm), claims


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(
        token, s.jwt_secret, algorithms=[s.jwt_algorithm], issuer="codeforge",
        options={"require": ["exp", "iat", "sub", "jti"]},
    )
