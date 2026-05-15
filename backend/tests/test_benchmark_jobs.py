from __future__ import annotations

import pytest
import sqlalchemy

from app.models.database import (
    AggregatedMetric,
    BenchmarkJob,
    BenchmarkJobStatus,
    Model,
    ModelStatus,
    ModelVersion,
    UserRole,
)
from app.services.benchmark_job_service import BenchmarkJobService


def _make_model_version(
    db,
    *,
    model_name: str = "bench-model",
    hf_model_id: str = "test/bench-model",
) -> tuple[Model, ModelVersion]:
    model = Model(name=model_name, source=f"hf:{hf_model_id}", status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    version = ModelVersion(
        model_id=model.id,
        version="v1",
        model_metadata={"hf_model_id": hf_model_id},
    )
    db.add(version)
    db.commit()
    db.refresh(model)
    db.refresh(version)
    return model, version


_DEFAULT_PARAMS = dict(
    dataset_id="wikitext-2",
    sample_count=4,
    max_new_tokens=16,
    temperature=0.7,
    num_beams=1,
    max_tokens=8000,
    top_k=20,
    rare_percentile=0.1,
    seed=42,
    created_by_id=None,
)

_FAKE_RESULT = {
    "entropy": 3.5,
    "perplexity": 11.3,
    "token_count": 50,
    "vocab_size": 40,
    "js_divergence": 0.02,
    "rare_token_percentage": 5.0,
    "prompts_used": 4,
    "top_tokens": [],
    "avg_sequence_perplexity": 12.0,
    "std_sequence_perplexity": 1.5,
    "reference_entropy": 3.2,
    "reference_perplexity": 9.2,
    "dataset": "WikiText-2 (raw)",
    "dataset_id": "wikitext-2",
}


def _fake_benchmark(**_):
    return _FAKE_RESULT


def test_create_job_stored_as_queued(db):
    _, version = _make_model_version(db)
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    assert job.id is not None
    assert job.status == BenchmarkJobStatus.QUEUED
    assert job.model_version_id == version.id
    assert job.dataset_id == "wikitext-2"
    assert job.seed == 42
    assert job.result is None
    assert job.started_at is None
    assert job.completed_at is None


def test_get_job_returns_existing(db):
    _, version = _make_model_version(db, model_name="get-job-model")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    fetched = BenchmarkJobService.get_job(db, job.id)
    assert fetched is not None
    assert fetched.id == job.id


def test_get_job_returns_none_for_missing(db):
    assert BenchmarkJobService.get_job(db, 99999) is None


def test_list_jobs_returns_all(db):
    _, version = _make_model_version(db, model_name="list-jobs-model")
    BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    jobs = BenchmarkJobService.list_jobs(db)
    assert len(jobs) == 2


def test_list_jobs_filtered_by_version(db):
    _, v1 = _make_model_version(db, model_name="lj-model-1", hf_model_id="test/lj1")
    model2 = Model(name="lj-model-2", source="hf:test/lj2", status=ModelStatus.ACTIVE)
    db.add(model2)
    db.flush()
    v2 = ModelVersion(model_id=model2.id, version="v1", model_metadata={"hf_model_id": "test/lj2"})
    db.add(v2)
    db.commit()
    db.refresh(v2)

    BenchmarkJobService.create_job(db, model_version_id=v1.id, **_DEFAULT_PARAMS)
    BenchmarkJobService.create_job(db, model_version_id=v2.id, **_DEFAULT_PARAMS)

    filtered = BenchmarkJobService.list_jobs(db, model_version_id=v1.id)
    assert len(filtered) == 1
    assert filtered[0].model_version_id == v1.id


def test_list_jobs_respects_limit(db):
    _, version = _make_model_version(db, model_name="lj-limit-model")
    for _ in range(5):
        BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    jobs = BenchmarkJobService.list_jobs(db, limit=2)
    assert len(jobs) == 2


def test_delete_job_returns_true(db):
    _, version = _make_model_version(db, model_name="del-job-model")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    assert BenchmarkJobService.delete_job(db, job.id) is True
    assert BenchmarkJobService.get_job(db, job.id) is None


def test_delete_missing_job_returns_false(db):
    assert BenchmarkJobService.delete_job(db, 99999) is False


def test_execute_job_success_sets_completed(db, monkeypatch):
    _, version = _make_model_version(db, model_name="ej-success")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    monkeypatch.setattr(
        "app.services.benchmark_job_service.calculate_wikitext_benchmark_metrics",
        _fake_benchmark,
    )

    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.status == BenchmarkJobStatus.COMPLETED
    assert job.result is not None
    assert job.result["entropy"] == pytest.approx(3.5)
    assert job.started_at is not None
    assert job.completed_at is not None


def test_execute_job_creates_aggregated_metric_snapshot(db, monkeypatch):
    _, version = _make_model_version(db, model_name="ej-snapshot")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    monkeypatch.setattr(
        "app.services.benchmark_job_service.calculate_wikitext_benchmark_metrics",
        _fake_benchmark,
    )
    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.aggregated_metric_id is not None
    snapshot = db.query(AggregatedMetric).filter(AggregatedMetric.id == job.aggregated_metric_id).first()
    assert snapshot is not None
    assert snapshot.model_version_id == version.id
    assert snapshot.metrics_data["benchmark_job_id"] == job.id


def test_execute_job_missing_job_id_is_noop(db):
    BenchmarkJobService.execute_job(db, 99999)


def test_execute_job_model_version_not_found_fails(db):
    _, version = _make_model_version(db, model_name="ej-vnf")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    # point the job at a non-existent version id via raw SQL
    db.execute(
        sqlalchemy.text("UPDATE benchmark_jobs SET model_version_id = 99999 WHERE id = :id"),
        {"id": job.id},
    )
    db.commit()

    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.status == BenchmarkJobStatus.FAILED
    assert job.error_message is not None
    assert "not found" in job.error_message.lower()


def test_execute_job_no_model_source_fails(db):
    model = Model(name="ej-nosrc", source=None, status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    version = ModelVersion(model_id=model.id, version="v1", model_metadata={})
    db.add(version)
    db.commit()
    db.refresh(version)

    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.status == BenchmarkJobStatus.FAILED
    assert job.error_message is not None


def test_execute_job_calculation_exception_sets_failed(db, monkeypatch):
    _, version = _make_model_version(db, model_name="ej-exc")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    def _boom(**kwargs):
        raise RuntimeError("GPU out of memory")

    monkeypatch.setattr(
        "app.services.benchmark_job_service.calculate_wikitext_benchmark_metrics",
        _boom,
    )

    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.status == BenchmarkJobStatus.FAILED
    assert "GPU out of memory" in (job.error_message or "")


def test_execute_job_uses_hf_source_from_model_when_no_metadata(db, monkeypatch):
    model = Model(name="ej-hfsrc", source="hf:test/from-source", status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    version = ModelVersion(model_id=model.id, version="v1")
    db.add(version)
    db.commit()
    db.refresh(version)

    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    captured: dict = {}

    def _capture(**kwargs):
        captured["model_id"] = kwargs.get("model_id")
        return _fake_benchmark(**kwargs)

    monkeypatch.setattr(
        "app.services.benchmark_job_service.calculate_wikitext_benchmark_metrics",
        _capture,
    )

    BenchmarkJobService.execute_job(db, job.id)

    assert captured.get("model_id") == "test/from-source"


def test_execute_job_uses_weights_path_when_no_hf_id(db, monkeypatch):
    model = Model(name="ej-weights", source=None, status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    version = ModelVersion(
        model_id=model.id,
        version="v1",
        model_metadata={},
        weights_path="/models/local-weights",
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    monkeypatch.setattr(
        "app.services.benchmark_job_service.calculate_wikitext_benchmark_metrics",
        _fake_benchmark,
    )

    BenchmarkJobService.execute_job(db, job.id)

    db.expire(job)
    db.refresh(job)
    assert job.status == BenchmarkJobStatus.COMPLETED


def _api_setup_version(real_client, model_name: str = "api-bench") -> dict:
    model = real_client.post(
        "/api/v1/models/",
        json={"name": model_name, "source": "hf:test/api-bench"},
    ).json()
    return real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={
            "model_id": model["id"],
            "version": "v1",
            "model_metadata": {"hf_model_id": "test/api-bench"},
        },
    ).json()


def test_submit_benchmark_returns_202_and_queued_status(client, login_as, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    version = _api_setup_version(real_client)

    # prevent background execution
    monkeypatch.setattr(
        "app.api.routes.analysis.BenchmarkJobService.execute_job",
        lambda db, job_id: None,
    )

    resp = real_client.post(
        "/api/v1/analysis/wikitext/benchmark",
        json={"model_version_id": version["id"], "dataset_id": "wikitext-2", "sample_count": 4, "max_new_tokens": 16},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["model_version_id"] == version["id"]
    assert body["dataset_id"] == "wikitext-2"
    assert body["id"] is not None


def test_submit_benchmark_404_missing_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/analysis/wikitext/benchmark",
        json={"model_version_id": 99999, "dataset_id": "wikitext-2"},
    )
    assert resp.status_code == 404


def test_submit_benchmark_400_no_model_source(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    model = real_client.post("/api/v1/models/", json={"name": "no-src-bench-model"}).json()
    version = real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={"model_id": model["id"], "version": "v1"},
    ).json()
    resp = real_client.post(
        "/api/v1/analysis/wikitext/benchmark",
        json={"model_version_id": version["id"], "dataset_id": "wikitext-2"},
    )
    assert resp.status_code == 400


def test_list_benchmark_jobs_returns_created_jobs(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    _, version = _make_model_version(db, model_name="http-list-bench")
    BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)
    BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    resp = real_client.get("/api/v1/analysis/wikitext/benchmark/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_list_benchmark_jobs_filtered_by_version(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    _, v1 = _make_model_version(db, model_name="http-lf-v1", hf_model_id="test/lf1")
    model2 = Model(name="http-lf-model2", source="hf:test/lf2", status=ModelStatus.ACTIVE)
    db.add(model2)
    db.flush()
    v2 = ModelVersion(model_id=model2.id, version="v1", model_metadata={"hf_model_id": "test/lf2"})
    db.add(v2)
    db.commit()
    db.refresh(v2)

    BenchmarkJobService.create_job(db, model_version_id=v1.id, **_DEFAULT_PARAMS)
    BenchmarkJobService.create_job(db, model_version_id=v2.id, **_DEFAULT_PARAMS)

    resp = real_client.get(f"/api/v1/analysis/wikitext/benchmark/jobs?model_version_id={v1.id}")
    assert resp.status_code == 200
    jobs = resp.json()
    assert all(j["model_version_id"] == v1.id for j in jobs)
    assert len(jobs) == 1


def test_get_benchmark_job_by_id(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    _, version = _make_model_version(db, model_name="http-get-bench")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    resp = real_client.get(f"/api/v1/analysis/wikitext/benchmark/jobs/{job.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job.id
    assert body["status"] == "queued"


def test_get_benchmark_job_404(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    assert real_client.get("/api/v1/analysis/wikitext/benchmark/jobs/99999").status_code == 404


def test_delete_benchmark_job_success(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    _, version = _make_model_version(db, model_name="http-del-bench")
    job = BenchmarkJobService.create_job(db, model_version_id=version.id, **_DEFAULT_PARAMS)

    resp = real_client.delete(f"/api/v1/analysis/wikitext/benchmark/jobs/{job.id}")
    assert resp.status_code == 204

    assert real_client.get(f"/api/v1/analysis/wikitext/benchmark/jobs/{job.id}").status_code == 404


def test_delete_benchmark_job_404(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    assert real_client.delete("/api/v1/analysis/wikitext/benchmark/jobs/99999").status_code == 404


def test_benchmark_jobs_require_auth(client):
    real_client, _ = client
    assert real_client.get("/api/v1/analysis/wikitext/benchmark/jobs").status_code == 401
