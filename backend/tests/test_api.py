from fastapi import Depends

from app.api.deps import require_role
from app.core.security import hash_password
from app.models import User
from app.models.enums import UserRole

PASSWORD = "a-long-test-password"


def make_user(db, email="analyst@example.com", role=UserRole.ANALYST, active=True):
    user = User(email=email, password_hash=hash_password(PASSWORD), role=role, is_active=active)
    db.add(user)
    db.commit()
    return user


def login(client, email="analyst@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.json()["db"] == "ok"


def test_login_me_refresh(client, db):
    make_user(db)
    r = login(client, email="ANALYST@example.com")  # citext: case-insensitive email
    assert r.status_code == 200
    tokens = r.json()

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.json() == {"id": 1, "email": "analyst@example.com", "role": "ANALYST"}

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    # an access token must not work as a refresh token
    bad = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert bad.status_code == 401


def test_login_rejects_bad_credentials_and_inactive(client, db):
    make_user(db)
    make_user(db, email="old@example.com", active=False)
    assert login(client, password="wrong-password").status_code == 401
    assert login(client, email="nobody@example.com").status_code == 401
    assert login(client, email="old@example.com").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401


def test_login_is_rate_limited(client, db):
    codes = [login(client, password="wrong-password").status_code for _ in range(6)]
    assert codes[-1] == 429


def test_require_role(client, db):
    from app.main import app

    @app.get("/test-admin-only")
    def admin_only(user=Depends(require_role(UserRole.ADMIN))):
        return {"ok": True}

    make_user(db)
    make_user(db, email="admin@example.com", role=UserRole.ADMIN)
    analyst = login(client).json()["access_token"]
    admin = login(client, email="admin@example.com").json()["access_token"]
    assert (
        client.get("/test-admin-only", headers={"Authorization": f"Bearer {analyst}"}).status_code
        == 403
    )
    assert (
        client.get("/test-admin-only", headers={"Authorization": f"Bearer {admin}"}).status_code
        == 200
    )
