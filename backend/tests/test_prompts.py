import pytest

from app.models.database import UserRole


def _setup_version(real_client, *, model_name: str = "test-model") -> dict:
    model = real_client.post(
        "/api/v1/models/",
        json={"name": model_name, "source": "hf:test/test"},
    ).json()
    version = real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={
            "model_id": model["id"],
            "version": "v1",
            "model_metadata": {"hf_model_id": "test/test"},
        },
    ).json()
    return version


def _setup_version_no_source(real_client, *, model_name: str = "nosrc-model") -> dict:
    """Create a model/version with no HF source (for generate-400 tests)."""
    model = real_client.post("/api/v1/models/", json={"name": model_name}).json()
    version = real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={"model_id": model["id"], "version": "v1"},
    ).json()
    return version


# ── existing tests (kept) ─────────────────────────────────────────────────────


def test_create_and_get_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    create = real_client.post(
        "/api/v1/prompts/",
        json={
            "model_version_id": version["id"],
            "input_text": "Tell me about transformers.",
            "temperature": 0.7,
            "max_new_tokens": 32,
        },
    )
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
        real_client.post(
            "/api/v1/prompts/",
            json={"model_version_id": version["id"], "input_text": f"prompt {i}", "max_new_tokens": 8},
        )
    resp = real_client.get("/api/v1/prompts/count")
    assert resp.status_code == 200
    assert resp.json() == {"count": 3}


def test_generate_endpoint_runs_stubbed_inference(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Generate me something.", "max_new_tokens": 8},
    ).json()
    resp = real_client.post(
        f"/api/v1/prompts/{prompt['id']}/generate",
        json={"max_new_tokens": 4, "temperature": 0.5},
    )
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


def test_save_response_accepts_text(client, login_as):
    """PUT /{id}/response stores supplied output (passed via query parameter)."""
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client)
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "hello", "max_new_tokens": 4},
    ).json()
    # output_text is exposed as a query parameter on this legacy endpoint
    resp = real_client.put(
        f"/api/v1/prompts/{prompt['id']}/response?output_text=stored%20response&generation_time_ms=12.5",
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_length"] == len("stored response")


# ── authentication ────────────────────────────────────────────────────────────


def test_prompts_requires_auth(client):
    real_client, _ = client
    resp = real_client.get("/api/v1/prompts/")
    assert resp.status_code == 401


def test_get_prompt_not_found(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/prompts/9999")
    assert resp.status_code == 404


# ── list / filter ─────────────────────────────────────────────────────────────


def test_list_prompts_filter_by_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    v1 = _setup_version(real_client, model_name="filter-model-a")
    model2 = real_client.post("/api/v1/models/", json={"name": "filter-model-b", "source": "hf:b/b"}).json()
    v2 = real_client.post(
        f"/api/v1/models/{model2['id']}/versions",
        json={"model_id": model2["id"], "version": "v1", "model_metadata": {"hf_model_id": "b/b"}},
    ).json()

    real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": v1["id"], "input_text": "v1 prompt", "max_new_tokens": 4},
    )
    real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": v2["id"], "input_text": "v2 prompt", "max_new_tokens": 4},
    )

    resp = real_client.get(f"/api/v1/prompts/?model_version_id={v1['id']}&limit=50")
    assert resp.status_code == 200
    prompts = resp.json()
    assert all(p["model_version_id"] == v1["id"] for p in prompts)
    assert len(prompts) == 1


# ── PUT /{id} – update prompt ─────────────────────────────────────────────────


def test_update_prompt_input_text(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="upd-model-api-1")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Original text", "max_new_tokens": 8},
    ).json()

    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}", json={"input_text": "Updated text"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["input_text"] == "Updated text"


def test_update_prompt_temperature(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="upd-model-api-2")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Test", "temperature": 0.7, "max_new_tokens": 8},
    ).json()

    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}", json={"temperature": 1.2})
    assert resp.status_code == 200, resp.text
    assert resp.json()["temperature"] == pytest.approx(1.2)


def test_update_prompt_empty_text_rejected(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="upd-model-api-3")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Test", "max_new_tokens": 4},
    ).json()

    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}", json={"input_text": "   "})
    assert resp.status_code == 400


def test_update_prompt_nothing_to_update_rejected(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="upd-model-api-4")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Test", "max_new_tokens": 4},
    ).json()

    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}", json={})
    assert resp.status_code == 400


def test_update_prompt_not_found(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.put("/api/v1/prompts/9999", json={"input_text": "x"})
    assert resp.status_code == 404


# ── DELETE /{id} ──────────────────────────────────────────────────────────────


def test_delete_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="del-model-api-1")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "To be deleted", "max_new_tokens": 4},
    ).json()

    resp = real_client.delete(f"/api/v1/prompts/{prompt['id']}")
    assert resp.status_code == 204

    get_resp = real_client.get(f"/api/v1/prompts/{prompt['id']}")
    assert get_resp.status_code == 404


def test_delete_prompt_not_found(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.delete("/api/v1/prompts/9999")
    assert resp.status_code == 404


# ── POST /batch ───────────────────────────────────────────────────────────────


def test_batch_create_prompts(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="batch-model-1")

    resp = real_client.post(
        "/api/v1/prompts/batch",
        json={
            "prompts": [
                {"model_version_id": version["id"], "input_text": "Prompt A", "max_new_tokens": 8},
                {"model_version_id": version["id"], "input_text": "Prompt B", "max_new_tokens": 8},
                {"model_version_id": version["id"], "input_text": "Prompt C", "max_new_tokens": 8},
            ]
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body) == 3
    texts = {p["input_text"] for p in body}
    assert "Prompt A" in texts and "Prompt B" in texts and "Prompt C" in texts


def test_batch_create_rejects_missing_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/prompts/batch",
        json={"prompts": [{"model_version_id": 9999, "input_text": "Missing", "max_new_tokens": 8}]},
    )
    assert resp.status_code == 404


# ── POST /{id}/metrics ────────────────────────────────────────────────────────


def test_calculate_metrics_after_generate(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="metrics-model-1")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Calculate metrics.", "max_new_tokens": 16},
    ).json()

    gen = real_client.post(
        f"/api/v1/prompts/{prompt['id']}/generate",
        json={"max_new_tokens": 8, "temperature": 0.7},
    )
    assert gen.status_code == 200, gen.text

    metrics_resp = real_client.post(f"/api/v1/prompts/{prompt['id']}/metrics")
    assert metrics_resp.status_code == 200, metrics_resp.text
    body = metrics_resp.json()
    assert body["prompt_id"] == prompt["id"]
    assert "entropy" in body


def test_calculate_metrics_is_idempotent(client, login_as):
    """Calling metrics twice should not fail and should return same prompt_id."""
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="metrics-model-2")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Idempotent metrics.", "max_new_tokens": 8},
    ).json()

    real_client.post(
        f"/api/v1/prompts/{prompt['id']}/generate",
        json={"max_new_tokens": 4, "temperature": 0.7},
    )

    r1 = real_client.post(f"/api/v1/prompts/{prompt['id']}/metrics")
    r2 = real_client.post(f"/api/v1/prompts/{prompt['id']}/metrics")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["prompt_id"] == r2.json()["prompt_id"]


def test_calculate_metrics_400_without_generation(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="metrics-model-3")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "No generate", "max_new_tokens": 4},
    ).json()

    resp = real_client.post(f"/api/v1/prompts/{prompt['id']}/metrics")
    assert resp.status_code == 400


def test_calculate_metrics_404_for_missing_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post("/api/v1/prompts/9999/metrics")
    assert resp.status_code == 404


# ── GET /{id}/metrics ─────────────────────────────────────────────────────────


def test_get_metrics_after_calculate(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="gm-model-1")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Metrics test.", "max_new_tokens": 8},
    ).json()

    real_client.post(
        f"/api/v1/prompts/{prompt['id']}/generate",
        json={"max_new_tokens": 4, "temperature": 0.7},
    )
    real_client.post(f"/api/v1/prompts/{prompt['id']}/metrics")

    resp = real_client.get(f"/api/v1/prompts/{prompt['id']}/metrics")
    assert resp.status_code == 200
    assert resp.json()["prompt_id"] == prompt["id"]


def test_get_metrics_404_if_not_calculated(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="gm-model-2")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "No metrics yet.", "max_new_tokens": 4},
    ).json()

    resp = real_client.get(f"/api/v1/prompts/{prompt['id']}/metrics")
    assert resp.status_code == 404


# ── generate – error paths ────────────────────────────────────────────────────


def test_generate_400_when_no_model_source(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version_no_source(real_client)

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Will fail generation", "max_new_tokens": 4},
    ).json()

    resp = real_client.post(f"/api/v1/prompts/{prompt['id']}/generate", json={})
    assert resp.status_code == 400


def test_generate_with_top_k_and_top_p(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="gen-params-model")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Test generation params", "max_new_tokens": 4},
    ).json()

    resp = real_client.post(
        f"/api/v1/prompts/{prompt['id']}/generate",
        json={"max_new_tokens": 4, "temperature": 0.9, "top_k": 50, "top_p": 0.95},
    )
    assert resp.status_code == 200, resp.text


def test_generate_503_when_model_load_fails(client, login_as, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="503-model")

    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "Will cause 503", "max_new_tokens": 4},
    ).json()

    # Override the autouse stub to raise on load
    def _failing_loader(model_id, local_path=None):
        raise OSError("CUDA out of memory")

    monkeypatch.setattr("app.api.routes.prompts._load_model_and_tokenizer", _failing_loader)

    resp = real_client.post(f"/api/v1/prompts/{prompt['id']}/generate", json={})
    assert resp.status_code == 503


# ── PUT /{id}/response – update with raw response ────────────────────────────


def test_update_response_404_for_missing_prompt(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    # output_text must be provided as a query param for legacy support; use the body via Body() PromptResponseUpdate instead
    resp = real_client.put(
        "/api/v1/prompts/9999/response?output_text=hello",
    )
    assert resp.status_code == 404


def test_update_response_400_without_output_text(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _setup_version(real_client, model_name="resp-model-1")
    prompt = real_client.post(
        "/api/v1/prompts/",
        json={"model_version_id": version["id"], "input_text": "hi", "max_new_tokens": 4},
    ).json()

    # No output_text provided in body or query — route must reject with 400
    resp = real_client.put(f"/api/v1/prompts/{prompt['id']}/response", json={"generation_time_ms": 0})
    assert resp.status_code == 400
