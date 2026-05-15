from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List, Optional
from app.db.session import get_db
from app.schemas.schemas import (
    AggregatedMetricResponse,
    VersionComparisonRequest,
    VersionComparisonResponse,
    ReportExportRequest,
    WikiTextBenchmarkResponse,
    BenchmarkJobCreate,
    BenchmarkJobResponse,
)
from app.services.analytics_service import AnalyticsService
from app.services.wikitext_service import (
    DEFAULT_DATASET_ID,
    calculate_wikitext_benchmark_metrics,
    list_available_datasets,
    store_custom_dataset,
)
from app.services.model_service import ModelVersionService
from app.services.model_service import ModelService
from app.services.benchmark_job_service import BenchmarkJobService
from app.api.dependencies import get_current_user
from app.models.database import User
from app.services.audit_service import AuditService
from app.models.database import AggregatedMetric

router = APIRouter(prefix="/analysis", tags=["Analysis"])


@router.post("/aggregate", response_model=AggregatedMetricResponse)
def aggregate_metrics(
    model_version_id: int,
    period_start: datetime,
    period_end: datetime,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aggregate metrics for a model version and time window."""
    version = ModelVersionService.get_version_by_id(db, model_version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")

    aggregated = AnalyticsService.aggregate_metrics(db, model_version_id, period_start, period_end)
    data = aggregated.__dict__.copy()
    data.pop("_sa_instance_state", None)
    AuditService.log(db, current_user.id, "create", "aggregated_metric", aggregated.id, None, data)
    return aggregated


@router.get("/aggregated", response_model=list[AggregatedMetricResponse])
def list_aggregated_metrics(
    model_version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List aggregated metrics for a model version."""
    records = db.query(AggregatedMetric).filter(
        AggregatedMetric.model_version_id == model_version_id
    ).order_by(AggregatedMetric.period_start.asc()).all()
    return records


@router.post("/compare", response_model=VersionComparisonResponse)
def compare_versions(
    request: VersionComparisonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compare two model versions using aggregated metrics."""
    v1 = ModelVersionService.get_version_by_id(db, request.version_id_1)
    v2 = ModelVersionService.get_version_by_id(db, request.version_id_2)
    if not v1 or not v2:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    comparison = AnalyticsService.compare_versions(db, request.version_id_1, request.version_id_2)
    report = AnalyticsService.generate_comparison_report(db, request.version_id_1, request.version_id_2)
    response = VersionComparisonResponse(
        version_1=v1,
        version_2=v2,
        metrics_comparison=comparison,
        changes=report.get("changes", [])
    )
    AuditService.log(db, current_user.id, "compare", "model_version", None, None, {"version_id_1": v1.id, "version_id_2": v2.id})
    return response


@router.post("/report")
def export_comparison_report(
    request: ReportExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate comparison report with highlighted changes and export as CSV/JSON."""
    report = AnalyticsService.generate_comparison_report(db, request.version_id_1, request.version_id_2)
    AuditService.log(db, current_user.id, "report", "model_version", None, None, {"version_id_1": request.version_id_1, "version_id_2": request.version_id_2})

    if request.format == "json":
        return report

    import pandas as pd
    from fastapi.responses import Response

    df = pd.DataFrame(report["changes"])
    csv_data = df.to_csv(index=False)
    return Response(content=csv_data, media_type="text/csv")


@router.get("/wikitext/datasets")
def get_wikitext_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return {"datasets": list_available_datasets(), "default_dataset_id": DEFAULT_DATASET_ID}


@router.post("/wikitext/datasets/upload")
async def upload_wikitext_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file must have a name")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    try:
        dataset = store_custom_dataset(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"status": "ok", "dataset": dataset}


@router.post(
    "/wikitext/benchmark",
    response_model=BenchmarkJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_wikitext_benchmark(
    payload: BenchmarkJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue a benchmark job and return immediately. Execution happens in a Celery worker."""
    version = ModelVersionService.get_version_by_id(db, payload.model_version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")

    model = ModelService.get_model_by_id(db, version.model_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    # pre-validate model source so the caller gets immediate feedback
    local_path = version.weights_path or None
    model_id = None
    if version.model_metadata and isinstance(version.model_metadata, dict):
        model_id = version.model_metadata.get("hf_model_id")
    if not model_id and model.source and model.source.startswith("hf:"):
        model_id = model.source.replace("hf:", "", 1)

    if not model_id and not local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No local weights_path or hf_model_id found for this version or model source",
        )

    job = BenchmarkJobService.create_job(
        db,
        model_version_id=payload.model_version_id,
        dataset_id=payload.dataset_id,
        sample_count=payload.sample_count,
        max_new_tokens=payload.max_new_tokens,
        temperature=payload.temperature,
        num_beams=payload.num_beams,
        max_tokens=payload.max_tokens,
        top_k=payload.top_k,
        rare_percentile=payload.rare_percentile,
        seed=payload.seed,
        created_by_id=current_user.id,
    )

    # try Celery first; fall back to a background thread when the broker is
    # unreachable so the API stays usable without Redis
    try:
        from app.tasks import run_benchmark_job
        run_benchmark_job.delay(job.id)
    except Exception:  # noqa: BLE001
        import threading
        from app.db.session import SessionLocal

        def _inline_runner(target_job_id: int) -> None:
            inline_db = SessionLocal()
            try:
                BenchmarkJobService.execute_job(inline_db, target_job_id)
            finally:
                inline_db.close()

        threading.Thread(target=_inline_runner, args=(job.id,), daemon=True).start()

    AuditService.log(
        db,
        current_user.id,
        "create",
        "benchmark_job",
        job.id,
        None,
        {"model_version_id": job.model_version_id, "dataset_id": job.dataset_id},
    )
    return job


@router.get("/wikitext/benchmark/jobs", response_model=List[BenchmarkJobResponse])
def list_benchmark_jobs(
    model_version_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List benchmark jobs ordered by creation time (newest first)."""
    return BenchmarkJobService.list_jobs(
        db,
        model_version_id=model_version_id,
        limit=limit,
    )


@router.get("/wikitext/benchmark/jobs/{job_id}", response_model=BenchmarkJobResponse)
def get_benchmark_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single benchmark job by ID. Used by the frontend to poll status/result."""
    job = BenchmarkJobService.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark job not found")
    return job


@router.delete("/wikitext/benchmark/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benchmark_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a benchmark job from history. Does not abort a running task."""
    existing = BenchmarkJobService.get_job(db, job_id)
    if not BenchmarkJobService.delete_job(db, job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark job not found")
    AuditService.log(
        db,
        current_user.id,
        "delete",
        "benchmark_job",
        job_id,
        {"model_version_id": existing.model_version_id, "status": existing.status.value} if existing else None,
        None,
    )
