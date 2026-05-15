import io
import json

from app.models.database import UserRole


def _create_model_and_version(real_client) -> dict:
    model = real_client.post(
        "/api/v1/models/",
        json={"name": "data-route-model", "source": "hf:test/test"},
    ).json()
    version = real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={
            "model_id": model["id"],
            "version": "v1",
            "model_metadata": {"hf_model_id": "test/test"},
        },
    ).json()
    return {"model": model, "version": version}


def test_export_requires_engineer_or_admin(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    resp = real_client.post(
        "/api/v1/data/export",
        json={"entity_type": "models", "format": "json"},
    )
    assert resp.status_code == 403


def test_export_models_as_json(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    _create_model_and_version(real_client)
    resp = real_client.post(
        "/api/v1/data/export",
        json={"entity_type": "models", "format": "json"},
    )
    assert resp.status_code == 200, resp.text
    rows = json.loads(resp.content)
    assert isinstance(rows, list) and rows
    assert any(r["name"] == "data-route-model" for r in rows)


def test_export_versions_as_csv_with_filter(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    bundle = _create_model_and_version(real_client)
    resp = real_client.post(
        "/api/v1/data/export",
        json={
            "entity_type": "versions",
            "format": "csv",
            "model_id": bundle["model"]["id"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.content.decode("utf-8")
    assert "version" in body.splitlines()[0]


def test_export_prompts_with_date_filter(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    bundle = _create_model_and_version(real_client)
    real_client.post(
        "/api/v1/prompts/",
        json={
            "model_version_id": bundle["version"]["id"],
            "input_text": "hello world",
        },
    )
    resp = real_client.post(
        "/api/v1/data/export",
        json={
            "entity_type": "prompts",
            "format": "json",
            "version_id": bundle["version"]["id"],
            "date_from": "2000-01-01T00:00:00",
            "date_to": "2099-01-01T00:00:00",
        },
    )
    assert resp.status_code == 200, resp.text
    rows = json.loads(resp.content)
    assert any(r["input_text"] == "hello world" for r in rows)


def test_export_metrics_entity(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/data/export",
        json={"entity_type": "metrics", "format": "json"},
    )
    assert resp.status_code == 200


def test_export_rejects_unknown_entity(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/data/export",
        json={"entity_type": "ghost", "format": "json"},
    )
    assert resp.status_code == 422


def test_import_models_via_json(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    payload = [
        {"name": "imported-1", "description": "via json"},
        {"name": "imported-2"},
    ]
    file = io.BytesIO(json.dumps(payload).encode("utf-8"))
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("models.json", file, "application/json")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ok", "imported": 2}

    listed = real_client.get("/api/v1/models/").json()
    assert {m["name"] for m in listed} >= {"imported-1", "imported-2"}


def test_import_models_via_csv(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    csv_text = "name,description\ncsv-1,first\ncsv-2,second\n"
    file = io.BytesIO(csv_text.encode("utf-8"))
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("models.csv", file, "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 2


def test_import_rejects_bad_content_type(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    file = io.BytesIO(b"name,description\nnope,nope\n")
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("models.csv", file, "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_import_rejects_unparseable_file(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    file = io.BytesIO(b"this is not json")
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("broken.json", file, "application/json")},
    )
    assert resp.status_code == 400
    assert "Failed to parse" in resp.json()["detail"]


def test_import_rejects_non_array_json(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    file = io.BytesIO(b'{"not": "an array"}')
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("not_array.json", file, "application/json")},
    )
    assert resp.status_code == 400


def test_import_with_validation_errors_returns_400(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    payload = [{"description": "no-name"}, {"name": "ok"}]
    file = io.BytesIO(json.dumps(payload).encode("utf-8"))
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("partial.json", file, "application/json")},
    )
    assert resp.status_code == 400
    assert "errors" in resp.json()["detail"]


def test_import_rejects_unknown_entity_type(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    file = io.BytesIO(b"[]")
    resp = real_client.post(
        "/api/v1/data/import?entity_type=ghosts",
        files={"file": ("empty.json", file, "application/json")},
    )
    assert resp.status_code == 422


def test_operator_cannot_import(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.OPERATOR)
    file = io.BytesIO(b"[]")
    resp = real_client.post(
        "/api/v1/data/import?entity_type=models",
        files={"file": ("empty.json", file, "application/json")},
    )
    assert resp.status_code == 403
