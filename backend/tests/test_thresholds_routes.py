from app.models.database import UserRole


def _payload(name: str = "high-entropy", **overrides) -> dict:
    base = {
        "name": name,
        "metric_name": "entropy",
        "threshold_value": 5.0,
        "comparison_operator": ">",
        "persistence_count": 1,
        "persistence_window_minutes": 0,
        "description": "test threshold",
    }
    base.update(overrides)
    return base


def test_list_thresholds_requires_auth(client):
    real_client, _ = client
    resp = real_client.get("/api/v1/thresholds/")
    assert resp.status_code == 401


def test_operator_cannot_list_thresholds(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.get("/api/v1/thresholds/")
    assert resp.status_code == 403


def test_admin_can_create_threshold(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/thresholds/", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "high-entropy"
    assert body["metric_name"] == "entropy"
    assert body["threshold_value"] == 5.0
    assert body["is_active"] is True


def test_create_threshold_with_group_key(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/thresholds/",
        json=_payload(
            name="grouped",
            group_key="latency-cluster",
            require_all_in_group=True,
            persistence_count=3,
            persistence_window_minutes=15,
        ),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["group_key"] == "latency-cluster"
    assert body["require_all_in_group"] is True
    assert body["persistence_count"] == 3


def test_list_thresholds_filters_by_active(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    real_client.post("/api/v1/thresholds/", json=_payload(name="active-1"))
    real_client.post(
        "/api/v1/thresholds/",
        json=_payload(name="inactive-1") | {"is_active": False},
    )

    active = real_client.get("/api/v1/thresholds/?is_active=true").json()
    inactive = real_client.get("/api/v1/thresholds/?is_active=false").json()
    all_rows = real_client.get("/api/v1/thresholds/").json()

    assert {t["name"] for t in active} == {"active-1"}
    assert {t["name"] for t in inactive} == {"inactive-1"}
    assert len(all_rows) == 2


def test_get_threshold_by_id(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/thresholds/", json=_payload()).json()
    resp = real_client.get(f"/api/v1/thresholds/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_threshold_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/thresholds/9999")
    assert resp.status_code == 404


def test_update_threshold_sets_new_value(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/thresholds/", json=_payload()).json()
    resp = real_client.put(
        f"/api/v1/thresholds/{created['id']}",
        json={"threshold_value": 9.9, "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["threshold_value"] == 9.9
    assert body["id"] == created["id"]


def test_update_threshold_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.put(
        "/api/v1/thresholds/9999",
        json={"threshold_value": 1.0},
    )
    assert resp.status_code == 404


def test_delete_threshold(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/thresholds/", json=_payload()).json()
    resp = real_client.delete(f"/api/v1/thresholds/{created['id']}")
    assert resp.status_code == 204
    resp2 = real_client.delete(f"/api/v1/thresholds/{created['id']}")
    assert resp2.status_code == 404


def test_delete_threshold_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.delete("/api/v1/thresholds/9999")
    assert resp.status_code == 404
