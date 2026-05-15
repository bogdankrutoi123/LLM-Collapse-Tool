from datetime import datetime, timedelta

from app.models.database import (
    AggregatedMetric,
    Model,
    ModelStatus,
    ModelVersion,
    UserRole,
)


def _create_two_versions(db) -> tuple[ModelVersion, ModelVersion]:
    model = Model(name="cmp-model", status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    v1 = ModelVersion(model_id=model.id, version="v1")
    v2 = ModelVersion(model_id=model.id, version="v2")
    db.add_all([v1, v2])
    db.commit()
    db.refresh(v1)
    db.refresh(v2)
    return v1, v2


def _seed_snapshot(db, version_id: int, *, entropy: float, js: float, perplexity: float):
    now = datetime.utcnow()
    db.add(
        AggregatedMetric(
            model_version_id=version_id,
            period_start=now,
            period_end=now,
            total_prompts=10,
            avg_entropy=entropy,
            avg_kl_divergence=js,
            avg_generation_time=None,
            avg_output_length=None,
            anomaly_count=0,
            anomaly_percentage=None,
            metrics_data={
                "benchmark": {
                    "entropy": entropy,
                    "perplexity": perplexity,
                    "js_divergence": js,
                    "rare_token_percentage": 12.5,
                    "vocab_size": 15000,
                    "avg_sequence_perplexity": perplexity * 1.1,
                }
            },
        )
    )
    db.commit()


def test_compare_versions_returns_real_data_after_benchmark_snapshot(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, v2 = _create_two_versions(db)
    _seed_snapshot(db, v1.id, entropy=4.2, js=0.05, perplexity=18.3)
    _seed_snapshot(db, v2.id, entropy=5.7, js=0.32, perplexity=29.1)

    resp = real_client.post(
        "/api/v1/analysis/compare",
        json={"version_id_1": v1.id, "version_id_2": v2.id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    metrics = {row["metric"] for row in body["changes"]}
    assert "avg_entropy" in metrics
    assert "perplexity" in metrics
    assert "js_divergence" in metrics
    js_row = next(r for r in body["changes"] if r["metric"] == "js_divergence")
    assert js_row["highlight"] is True
    assert js_row["delta"] is not None and js_row["delta"] > 0.2


def test_aggregated_listing_orders_by_period_start(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, _v2 = _create_two_versions(db)
    base = datetime.utcnow()
    for i in range(3):
        ts = base - timedelta(days=i)
        db.add(
            AggregatedMetric(
                model_version_id=v1.id,
                period_start=ts,
                period_end=ts,
                total_prompts=1,
                avg_entropy=float(i),
                avg_kl_divergence=0.1 * i,
                anomaly_count=0,
            )
        )
    db.commit()

    resp = real_client.get(f"/api/v1/analysis/aggregated?model_version_id={v1.id}")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    timestamps = [r["period_start"] for r in rows]
    assert timestamps == sorted(timestamps)


def test_export_report_csv(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, v2 = _create_two_versions(db)
    _seed_snapshot(db, v1.id, entropy=4.0, js=0.1, perplexity=20.0)
    _seed_snapshot(db, v2.id, entropy=4.5, js=0.2, perplexity=22.0)

    resp = real_client.post(
        "/api/v1/analysis/report",
        json={"version_id_1": v1.id, "version_id_2": v2.id, "format": "csv"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "metric" in resp.text and "delta" in resp.text


def test_export_report_json(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, v2 = _create_two_versions(db)
    _seed_snapshot(db, v1.id, entropy=3.0, js=0.05, perplexity=15.0)
    _seed_snapshot(db, v2.id, entropy=3.8, js=0.15, perplexity=18.0)

    resp = real_client.post(
        "/api/v1/analysis/report",
        json={"version_id_1": v1.id, "version_id_2": v2.id, "format": "json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "changes" in body
    assert isinstance(body["changes"], list)


def test_compare_versions_404_missing_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/analysis/compare",
        json={"version_id_1": 99999, "version_id_2": 99998},
    )
    assert resp.status_code == 404


def test_compare_versions_uses_raw_metrics_when_no_snapshot(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, v2 = _create_two_versions(db)
    resp = real_client.post(
        "/api/v1/analysis/compare",
        json={"version_id_1": v1.id, "version_id_2": v2.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "changes" in body


def test_aggregate_metrics_creates_record(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, _ = _create_two_versions(db)
    now = datetime.utcnow()
    resp = real_client.post(
        f"/api/v1/analysis/aggregate"
        f"?model_version_id={v1.id}"
        f"&period_start={now.isoformat()}"
        f"&period_end={now.isoformat()}",
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["model_version_id"] == v1.id


def test_aggregate_metrics_404_for_missing_version(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    now = datetime.utcnow()
    resp = real_client.post(
        f"/api/v1/analysis/aggregate"
        f"?model_version_id=99999"
        f"&period_start={now.isoformat()}"
        f"&period_end={now.isoformat()}",
    )
    assert resp.status_code == 404


def test_get_wikitext_datasets(client, login_as, tmp_path, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)

    resp = real_client.get("/api/v1/analysis/wikitext/datasets")
    assert resp.status_code == 200
    body = resp.json()
    assert "datasets" in body
    assert "default_dataset_id" in body
    ids = [d["id"] for d in body["datasets"]]
    assert "wikitext-2" in ids


def test_upload_dataset_txt(client, login_as, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    monkeypatch.setattr(
        "app.api.routes.analysis.store_custom_dataset",
        lambda name, content: {"id": f"custom:{name}", "label": f"Custom: {name}"},
    )

    resp = real_client.post(
        "/api/v1/analysis/wikitext/datasets/upload",
        files={"file": ("mydata.txt", b"line one\nline two", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["dataset"]["id"] == "custom:mydata.txt"


def test_upload_dataset_empty_file_rejected(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.post(
        "/api/v1/analysis/wikitext/datasets/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400


def test_upload_dataset_invalid_extension_returns_400(client, login_as, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    def _bad_store(name, content):
        raise ValueError("Unsupported dataset format '.xyz'")

    monkeypatch.setattr("app.api.routes.analysis.store_custom_dataset", _bad_store)

    resp = real_client.post(
        "/api/v1/analysis/wikitext/datasets/upload",
        files={"file": ("bad.xyz", b"some content", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_benchmark_endpoint_requires_auth(client):
    real_client, _ = client
    resp = real_client.post(
        "/api/v1/analysis/wikitext/benchmark",
        json={"model_version_id": 1, "dataset_id": "wikitext-2"},
    )
    assert resp.status_code == 401


def test_list_benchmark_jobs_empty_when_none(client, login_as):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)
    resp = real_client.get("/api/v1/analysis/wikitext/benchmark/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_submit_benchmark_job_with_seed(client, login_as, monkeypatch):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    model = real_client.post(
        "/api/v1/models/",
        json={"name": "seed-bench-model", "source": "hf:test/seed-bench"},
    ).json()
    version = real_client.post(
        f"/api/v1/models/{model['id']}/versions",
        json={
            "model_id": model["id"],
            "version": "v1",
            "model_metadata": {"hf_model_id": "test/seed-bench"},
        },
    ).json()

    # prevent background execution
    monkeypatch.setattr(
        "app.api.routes.analysis.BenchmarkJobService.execute_job",
        lambda db, job_id: None,
    )

    resp = real_client.post(
        "/api/v1/analysis/wikitext/benchmark",
        json={
            "model_version_id": version["id"],
            "dataset_id": "wikitext-2",
            "sample_count": 4,
            "seed": 123,
        },
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["seed"] == 123
