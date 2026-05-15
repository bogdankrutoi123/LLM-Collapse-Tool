from app.models.database import UserRole


def _rule_payload(name: str = "rule-A", **overrides) -> dict:
    base = {
        "name": name,
        "operator": "any",
        "description": "drift composite",
        "is_active": True,
        "items": [
            {
                "metric_name": "entropy",
                "threshold_value": 5.0,
                "comparison_operator": ">",
                "persistence_count": 1,
                "persistence_window_minutes": 0,
            },
            {
                "metric_name": "js_divergence",
                "threshold_value": 0.5,
                "comparison_operator": ">=",
                "persistence_count": 2,
                "persistence_window_minutes": 5,
            },
        ],
    }
    base.update(overrides)
    return base


def test_list_rules_requires_auth(client):
    real_client, _ = client
    resp = real_client.get("/api/v1/rules/")
    assert resp.status_code == 401


def test_operator_cannot_list_rules(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.get("/api/v1/rules/")
    assert resp.status_code == 403


def test_admin_can_create_rule_with_items(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/rules/", json=_rule_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "rule-A"
    assert body["operator"] == "any"
    assert len(body["items"]) == 2
    assert {item["metric_name"] for item in body["items"]} == {
        "entropy",
        "js_divergence",
    }


def test_create_rule_with_all_operator_and_no_items(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/rules/",
        json=_rule_payload(name="empty-rule", operator="all", items=[]),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["items"] == []


def test_list_rules_filters_by_active(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    real_client.post("/api/v1/rules/", json=_rule_payload(name="active-rule"))
    real_client.post(
        "/api/v1/rules/",
        json=_rule_payload(name="inactive-rule") | {"is_active": False},
    )

    active = real_client.get("/api/v1/rules/?is_active=true").json()
    inactive = real_client.get("/api/v1/rules/?is_active=false").json()
    assert {r["name"] for r in active} == {"active-rule"}
    assert {r["name"] for r in inactive} == {"inactive-rule"}


def test_list_rules_supports_pagination(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    for i in range(5):
        real_client.post("/api/v1/rules/", json=_rule_payload(name=f"r-{i}", items=[]))
    page1 = real_client.get("/api/v1/rules/?skip=0&limit=2").json()
    page2 = real_client.get("/api/v1/rules/?skip=2&limit=2").json()
    assert len(page1) == 2
    assert len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_get_rule_by_id(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/rules/", json=_rule_payload()).json()
    resp = real_client.get(f"/api/v1/rules/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_rule_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/rules/9999")
    assert resp.status_code == 404


def test_update_rule(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/rules/", json=_rule_payload()).json()
    resp = real_client.put(
        f"/api/v1/rules/{created['id']}",
        json={"name": "renamed-rule", "operator": "all", "is_active": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "renamed-rule"
    assert body["operator"] == "all"
    assert body["is_active"] is False


def test_update_rule_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.put("/api/v1/rules/9999", json={"name": "ghost"})
    assert resp.status_code == 404


def test_replace_rule_items(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/rules/", json=_rule_payload()).json()
    new_items = [
        {
            "metric_name": "wasserstein_distance",
            "threshold_value": 1.5,
            "comparison_operator": ">=",
            "persistence_count": 1,
            "persistence_window_minutes": 0,
        }
    ]
    resp = real_client.put(
        f"/api/v1/rules/{created['id']}/items",
        json=new_items,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["metric_name"] == "wasserstein_distance"


def test_replace_rule_items_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.put("/api/v1/rules/9999/items", json=[])
    assert resp.status_code == 404


def test_delete_rule(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    created = real_client.post("/api/v1/rules/", json=_rule_payload()).json()
    resp = real_client.delete(f"/api/v1/rules/{created['id']}")
    assert resp.status_code == 204
    resp2 = real_client.delete(f"/api/v1/rules/{created['id']}")
    assert resp2.status_code == 404


def test_delete_rule_returns_404_for_unknown(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.delete("/api/v1/rules/9999")
    assert resp.status_code == 404
