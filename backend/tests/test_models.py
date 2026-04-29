from app.models.database import UserRole


def test_models_list_requires_auth(client):
    real_client, _ = client
    resp = real_client.get("/api/v1/models/")
    assert resp.status_code == 401


def test_admin_can_create_model(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/models/",
                            json={"name": "phi-1.5", "description": "tiny", "source": "hf:microsoft/phi-1_5"})
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["name"] == "phi-1.5"


def test_operator_cannot_create_model(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.post("/api/v1/models/", json={"name": "denied", "description": ""})
    assert resp.status_code == 403


def test_engineer_can_create_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.MODEL_ENGINEER)
    model = real_client.post("/api/v1/models/",
                             json={"name": "test-model", "source": "hf:test/test"}).json()
    resp = real_client.post(f"/api/v1/models/{model['id']}/versions",
                            json={"model_id": model["id"], "version": "v1.0",
                                  "model_metadata": {"hf_model_id": "test/test"}})
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["version"] == "v1.0"


def test_list_versions_for_model(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    model = real_client.post("/api/v1/models/", json={"name": "model-with-versions"}).json()
    for tag in ("v1", "v2", "v3"):
        real_client.post(f"/api/v1/models/{model['id']}/versions",
                         json={"model_id": model["id"], "version": tag})
    resp = real_client.get(f"/api/v1/models/{model['id']}/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 3
    assert {v["version"] for v in versions} == {"v1", "v2", "v3"}


def test_admin_can_delete_model(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    model = real_client.post("/api/v1/models/", json={"name": "to-delete"}).json()
    delete = real_client.delete(f"/api/v1/models/{model['id']}")
    assert delete.status_code in (200, 204)


def test_get_missing_model_returns_404(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/models/9999")
    assert resp.status_code == 404
