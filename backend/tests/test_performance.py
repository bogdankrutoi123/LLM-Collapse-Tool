import pytest

from app.models.database import UserRole

pytestmark = pytest.mark.perf


def test_perf_warm_login_loop(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    for _ in range(100):
        resp = real_client.get("/api/v1/auth/me")
        assert resp.status_code == 200


def test_perf_models_listing_under_load(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    for i in range(50):
        real_client.post("/api/v1/models/", json={"name": f"perf-model-{i}"})
    for _ in range(50):
        resp = real_client.get("/api/v1/models/?limit=200")
        assert resp.status_code == 200
        assert len(resp.json()) >= 50


def test_perf_prompt_create_then_count(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    model = real_client.post("/api/v1/models/", json={"name": "perf-model"}).json()
    version = real_client.post(f"/api/v1/models/{model['id']}/versions",
                               json={"model_id": model["id"], "version": "v1"}).json()
    for i in range(40):
        real_client.post("/api/v1/prompts/", json={
            "model_version_id": version["id"],
            "input_text": f"performance prompt {i}",
            "max_new_tokens": 8,
        })
    resp = real_client.get("/api/v1/prompts/count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 40


def test_perf_generate_throughput(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    model = real_client.post("/api/v1/models/", json={"name": "gen-model"}).json()
    version = real_client.post(f"/api/v1/models/{model['id']}/versions",
                               json={"model_id": model["id"], "version": "v1",
                                     "model_metadata": {"hf_model_id": "stub/model"}}).json()
    ids = []
    for i in range(20):
        prompt = real_client.post("/api/v1/prompts/", json={
            "model_version_id": version["id"],
            "input_text": f"prompt {i}",
            "max_new_tokens": 4,
        }).json()
        ids.append(prompt["id"])
    for pid in ids:
        resp = real_client.post(f"/api/v1/prompts/{pid}/generate", json={})
        assert resp.status_code == 200
