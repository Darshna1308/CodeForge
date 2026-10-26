import time

import jwt
from sqlalchemy import select

from codeforge_core.config import get_settings
from codeforge_core.db import get_sessionmaker
from codeforge_core.models import User

from api_helpers import register


def test_register_login_me_logout(client):
    name, headers = register(client)
    assert client.get("/auth/me", headers=headers).json()["username"] == name
    r = client.post("/auth/login", json={"username": name.upper(), "password": "s3cure-password!"})
    assert r.status_code == 200 and "cf_session" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    client.cookies.clear()
    token = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.post("/auth/logout", headers=token).status_code == 204
    r = client.get("/auth/me", headers=token)
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_revoked"


def test_password_is_hashed_with_argon2(client):
    name, _ = register(client)
    with get_sessionmaker()() as s:
        user = s.execute(select(User).where(User.username == name)).scalar_one()
    assert "s3cure-password!" not in user.password_hash
    assert user.password_hash.startswith("$argon2id$")


def test_duplicate_username_conflicts_case_insensitively(client):
    name, _ = register(client)
    r = client.post("/auth/register", json={"username": name.upper(), "email": f"other_{name}@example.com", "password": "s3cure-password!"})
    assert r.status_code == 409


def test_bad_credentials_and_validation(client):
    name, _ = register(client)
    assert client.post("/auth/login", json={"username": name, "password": "wrong"}).status_code == 401
    assert client.post("/auth/login", json={"username": "nobody_here", "password": "x"}).status_code == 401
    r = client.post("/auth/register", json={"username": "x", "email": "bad", "password": "short"})
    assert r.status_code == 422
    assert {d["loc"][-1] for d in r.json()["error"]["details"]} == {"username", "email", "password"}


def test_expired_and_forged_tokens_rejected(client):
    s = get_settings()
    now = int(time.time())
    expired = jwt.encode({"sub": "1", "jti": "x", "iat": now - 100, "exp": now - 10, "iss": "codeforge"}, s.jwt_secret, algorithm="HS256")
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    forged = jwt.encode({"sub": "1", "jti": "x", "iat": now, "exp": now + 100, "iss": "codeforge"}, "not-the-secret-at-all", algorithm="HS256")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_session_endpoint_is_anonymous_friendly(client):
    client.cookies.clear()
    assert client.get("/auth/session").json() == {"user": None}
