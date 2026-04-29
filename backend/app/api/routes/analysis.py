from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime
from app.db.session import get_db
from app.schemas.schemas import AggregatedMetricResponse, VersionComparisonRequest, VersionComparisonResponse, ReportExportRequest, WikiTextBenchmarkResponse
from app.services.analytics_service import AnalyticsService
from app.services.wikitext_service import (
    DEFAULT_DATASET_ID,
    calculate_wikitext_benchmark_metrics,
    list_available_datasets,
    store_custom_dataset,
)
from app.services.model_service import ModelVersionService
from app.services.model_service import ModelService
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


@router.get("/wikitext/benchmark", response_model=WikiTextBenchmarkResponse)
def get_wikitext_benchmark(
    model_version_id: int,
    dataset_id: str = DEFAULT_DATASET_ID,
    sample_count: int = 8,
    max_new_tokens: int = 32,
    temperature: float = 0.7,
    num_beams: int = 1,
    max_tokens: int = 8000,
    top_k: int = 20,
    rare_percentile: float = 0.1,
    seed: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Benchmark token metrics on model-generated continuations of WikiText-2 prompts."""
    if sample_count < 1 or sample_count > 200:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sample_count must be between 1 and 200")
    if max_new_tokens < 1 or max_new_tokens > 512:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_new_tokens must be between 1 and 512")
    if max_tokens < 1000 or max_tokens > 200000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_tokens must be between 1000 and 200000")
    if num_beams < 1 or num_beams > 10:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="num_beams must be between 1 and 10")
    if top_k < 5 or top_k > 100:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="top_k must be between 5 and 100")
    if rare_percentile <= 0 or rare_percentile >= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rare_percentile must be between 0 and 1")

    version = ModelVersionService.get_version_by_id(db, model_version_id)
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model version not found")

    model = ModelService.get_model_by_id(db, version.model_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    local_path = version.weights_path or None
    model_id = None
    if version.model_metadata and isinstance(version.model_metadata, dict):
        model_id = version.model_metadata.get("hf_model_id")
    if not model_id and model.source and model.source.startswith("hf:"):
        model_id = model.source.replace("hf:", "", 1)

    if not model_id and not local_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No local weights_path or hf_model_id found for this version or model source"
        )

    try:
        result = calculate_wikitext_benchmark_metrics(
            model_id=model_id,
            dataset_id=dataset_id,
            local_path=local_path,
            sample_count=sample_count,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            num_beams=num_beams,
            max_tokens=max_tokens,
            top_k=top_k,
            rare_percentile=rare_percentile,
            seed=seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Benchmark failed unexpectedly: {exc.__class__.__name__}: {exc}",
        ) from exc

    now = datetime.utcnow()
    snapshot = AggregatedMetric(
        model_version_id=model_version_id,
        period_start=now,
        period_end=now,
        total_prompts=result["prompts_used"],
        avg_entropy=result["entropy"],
        avg_kl_divergence=None,
        avg_generation_time=None,
        avg_output_length=None,
        anomaly_count=0,
        anomaly_percentage=0.0,
        metrics_data={"benchmark": result},
    )
    db.add(snapshot)
    db.commit()

    return result
