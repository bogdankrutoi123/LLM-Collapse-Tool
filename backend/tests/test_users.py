from app.models.database import UserRole


def test_operator_cannot_list_users(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.get("/api/v1/users/")
    assert resp.status_code == 403


def test_admin_can_list_users(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/users/")
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert "admin" in usernames


def test_admin_can_create_user(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/users/", json={
        "email": "fresh@example.com",
        "username": "fresh",
        "password": "password1234",
        "role": "model_engineer",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "model_engineer"


def test_admin_can_change_role(client, login_as, make_user):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    target = make_user(username="promote-me", role=UserRole.OPERATOR)
    resp = real_client.put(f"/api/v1/users/{target.id}", json={"role": "admin"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "admin"


def test_admin_can_deactivate_user(client, login_as, make_user):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    target = make_user(username="kickme", role=UserRole.OPERATOR)
    resp = real_client.put(f"/api/v1/users/{target.id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
