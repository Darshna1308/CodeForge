import uuid


def register(client, prefix="u"):
    name = f"{prefix}_{uuid.uuid4().hex[:10]}"
    r = client.post("/auth/register", json={"username": name, "email": f"{name}@example.com", "password": "s3cure-password!"})
    assert r.status_code == 201, r.text
    client.cookies.clear()  # tests authenticate explicitly with bearer tokens
    return name, {"Authorization": f"Bearer {r.json()['access_token']}"}
