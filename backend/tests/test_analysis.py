from datetime import datetime, timedelta

from app.models.database import (
    AggregatedMetric, Model, ModelStatus, ModelVersion, UserRole,
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
    db.add(AggregatedMetric(
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
    ))
    db.commit()


def test_compare_versions_returns_real_data_after_benchmark_snapshot(client, login_as, db):
    real_client, _ = client
    login_as(role=UserRole.ADMIN)

    v1, v2 = _create_two_versions(db)
    _seed_snapshot(db, v1.id, entropy=4.2, js=0.05, perplexity=18.3)
    _seed_snapshot(db, v2.id, entropy=5.7, js=0.32, perplexity=29.1)

    resp = real_client.post("/api/v1/analysis/compare",
                            json={"version_id_1": v1.id, "version_id_2": v2.id})
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
        db.add(AggregatedMetric(
            model_version_id=v1.id,
            period_start=ts, period_end=ts,
            total_prompts=1,
            avg_entropy=float(i),
            avg_kl_divergence=0.1 * i,
            anomaly_count=0,
        ))
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

    resp = real_client.post("/api/v1/analysis/report",
                            json={"version_id_1": v1.id, "version_id_2": v2.id, "format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "metric" in resp.text and "delta" in resp.text
