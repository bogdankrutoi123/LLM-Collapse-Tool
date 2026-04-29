from app.models.database import UserRole


def _setup_version(real_client) -> dict:
    model = real_client.post("/api/v1/models/",
                             json={"name": "test-model", "source": "hf:test/test"}).json()
    version = real_client.post(f"/api/v1/models/{model['id']}/versions",
                               json={"model_id": model["id"], "version": "v1",
                                     "model_metadata": {"hf_model_id": "test/test"}}).json()
    return version


def test_create_and_get_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    create = real_client.post("/api/v1/prompts/", json={
        "model_version_id": version["id"],
        "input_text": "Tell me about transformers.",
        "temperature": 0.7,
        "max_new_tokens": 32,
    })
    assert create.status_code == 201, create.text
    prompt = create.json()
    assert prompt["input_text"].startswith("Tell me")
    fetched = real_client.get(f"/api/v1/prompts/{prompt['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == prompt["id"]


def test_prompt_count_endpoint(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    for i in range(3):
        real_client.post("/api/v1/prompts/", json={
            "model_version_id": version["id"],
            "input_text": f"prompt {i}",
            "max_new_tokens": 8,
        })
    resp = real_client.get("/api/v1/prompts/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}


def test_generate_endpoint_runs_stubbed_inference(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    prompt = real_client.post("/api/v1/prompts/", json={
        "model_version_id": version["id"],
        "input_text": "Generate me something.",
        "max_new_tokens": 8,
    }).json()
    resp = real_client.post(f"/api/v1/prompts/{prompt['id']}/generate",
                            json={"max_new_tokens": 4, "temperature": 0.5})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["output_text"] == "stub-generated text"
    assert body["output_length"] > 0
    assert body["generation_time_ms"] is not None and body["generation_time_ms"] >= 0


def test_generate_404_for_unknown_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/prompts/999/generate", json={})
    assert resp.status_code == 404


def test_save_response_accepts_empty_output(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    prompt = real_client.post("/api/v1/prompts/", json={
        "model_version_id": version["id"],
        "input_text": "hello",
        "max_new_tokens": 4,
    }).json()
    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}/response",
                           json={"output_text": "", "generation_time_ms": 12.5})
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_length"] == 0
