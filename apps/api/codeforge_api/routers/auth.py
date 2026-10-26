import time

import redis
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from codeforge_core import keys
from codeforge_core.config import get_settings
from codeforge_core.models import User

from ..deps import get_current_user, get_db, get_optional_user, get_r, get_token_claims
from ..errors import APIError
from ..ratelimit import limit_ip
from ..schemas import AuthOut, LoginIn, RegisterIn, UserOut
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(response: Response, user: User) -> AuthOut:
    s = get_settings()
    token, claims = create_token(user.id, user.username, user.role.value)
    response.set_cookie(
        s.auth_cookie_name, token, max_age=s.jwt_ttl_minutes * 60, httponly=True,
        secure=s.auth_cookie_secure, samesite="lax", path="/",
    )
    return AuthOut(user=UserOut.model_validate(user), access_token=token, expires_at=claims["exp"])


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(limit_ip("auth", "rate_limit_auth"))])
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> AuthOut:
    user = User(username=body.username, email=body.email.lower(), password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # The unique indexes are the source of truth (no check-then-insert race).
        db.rollback()
        raise APIError(409, "conflict", "Username or email is already registered")
    db.refresh(user)
    return _issue(response, user)


@router.post("/login", response_model=AuthOut, dependencies=[Depends(limit_ip("auth", "rate_limit_auth"))])
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)) -> AuthOut:
    ident = body.username.lower()
    user = db.execute(
        select(User).where(or_(func.lower(User.username) == ident, func.lower(User.email) == ident))
    ).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        raise APIError(401, "invalid_credentials", "Invalid username or password")
    return _issue(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, claims: dict | None = Depends(get_token_claims), r: redis.Redis = Depends(get_r)) -> Response:
    """Revokes the current token (denylist entry lives until the token's own expiry)."""
    if claims:
        ttl = max(1, int(claims["exp"] - time.time()))
        try:
            r.set(keys.revoked_token(claims["jti"]), "1", ex=ttl)
        except redis.RedisError:
            raise APIError(503, "unavailable", "Could not revoke session; try again")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().auth_cookie_name, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/session")
def session(user: User | None = Depends(get_optional_user)) -> dict:
    """Like /auth/me but returns 200 with ``user: null`` when logged out (no console noise for the SPA)."""
    return {"user": UserOut.model_validate(user).model_dump(mode="json") if user else None}
