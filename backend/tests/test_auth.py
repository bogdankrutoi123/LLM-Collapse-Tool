from app.models.database import UserRole


def test_register_public_creates_operator(client):
    real_client, _ = client
    resp = real_client.post("/api/v1/auth/register", json={
        "email": "newbie@example.com",
        "username": "newbie",
        "password": "complexpass123",
        "full_name": "New Bie",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "newbie"
    assert body["role"] == UserRole.OPERATOR.value


def test_register_forces_operator_role(client):
    real_client, _ = client
    resp = real_client.post("/api/v1/auth/register", json={
        "email": "sneaky@example.com",
        "username": "sneaky",
        "password": "complexpass123",
        "role": "admin",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "operator"


def test_register_rejects_duplicate(client, make_user):
    real_client, _ = client
    make_user(username="dup", email="dup@example.com")
    resp = real_client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "username": "dup",
        "password": "complexpass123",
    })
    assert resp.status_code == 400


def test_login_sets_cookies_and_returns_user(client, make_user):
    real_client, _ = client
    make_user(username="alice", password="alicespassword")
    resp = real_client.post("/api/v1/auth/login",
                            json={"username": "alice", "password": "alicespassword"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"
    assert "llm_access_token" in resp.cookies
    assert "llm_refresh_token" in resp.cookies


def test_login_wrong_password_rejected(client, make_user):
    real_client, _ = client
    make_user(username="bob", password="rightpassword")
    resp = real_client.post("/api/v1/auth/login",
                            json={"username": "bob", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_me_requires_auth(client):
    real_client, _ = client
    resp = real_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user_after_login(client, make_user):
    real_client, _ = client
    make_user(username="carol", password="carolspassword")
    real_client.post("/api/v1/auth/login",
                     json={"username": "carol", "password": "carolspassword"})
    me = real_client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "carol"


def test_refresh_rotates_session(client, make_user):
    real_client, _ = client
    make_user(username="dave", password="davespassword")
    real_client.post("/api/v1/auth/login",
                     json={"username": "dave", "password": "davespassword"})
    resp = real_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["username"] == "dave"


def test_refresh_without_cookie_rejected(client):
    real_client, _ = client
    real_client.cookies.clear()
    resp = real_client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


def test_logout_clears_session(client, make_user):
    real_client, _ = client
    make_user(username="eve", password="evespassword")
    real_client.post("/api/v1/auth/login",
                     json={"username": "eve", "password": "evespassword"})
    out = real_client.post("/api/v1/auth/logout")
    assert out.status_code == 204
    real_client.cookies.clear()
    after = real_client.get("/api/v1/auth/me")
    assert after.status_code == 401


def test_bootstrap_admin_happy_path(client):
    real_client, _ = client
    resp = real_client.post("/api/v1/auth/bootstrap-admin", json={
        "email": "root@example.com",
        "username": "root",
        "full_name": "Root User",
        "password": "verysecurepw1",
        "bootstrap_token": "test-bootstrap-token",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "admin"


def test_bootstrap_admin_rejects_bad_token(client):
    real_client, _ = client
    resp = real_client.post("/api/v1/auth/bootstrap-admin", json={
        "email": "root@example.com",
        "username": "root",
        "password": "verysecurepw1",
        "bootstrap_token": "wrong-token",
    })
    assert resp.status_code == 403


def test_bootstrap_admin_refuses_when_admin_exists(client, make_user):
    real_client, _ = client
    make_user(username="existing-admin", role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/auth/bootstrap-admin", json={
        "email": "root2@example.com",
        "username": "root2",
        "password": "verysecurepw1",
        "bootstrap_token": "test-bootstrap-token",
    })
    assert resp.status_code == 409
