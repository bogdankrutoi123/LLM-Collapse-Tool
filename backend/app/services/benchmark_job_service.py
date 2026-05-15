from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.database import (
    AggregatedMetric,
    BenchmarkJob,
    BenchmarkJobStatus,
    Model,
    ModelVersion,
)
from app.services.wikitext_service import calculate_wikitext_benchmark_metrics


class BenchmarkJobService:
    """Service to create and run asynchronous benchmark jobs."""

    @staticmethod
    def create_job(
        db: Session,
        *,
        model_version_id: int,
        dataset_id: str,
        sample_count: int,
        max_new_tokens: int,
        temperature: float,
        num_beams: int,
        max_tokens: int,
        top_k: int,
        rare_percentile: float,
        seed: Optional[int],
        created_by_id: Optional[int],
    ) -> BenchmarkJob:
        job = BenchmarkJob(
            model_version_id=model_version_id,
            created_by_id=created_by_id,
            status=BenchmarkJobStatus.QUEUED,
            dataset_id=dataset_id,
            sample_count=sample_count,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            num_beams=num_beams,
            max_tokens=max_tokens,
            top_k=top_k,
            rare_percentile=rare_percentile,
            seed=seed,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_job(db: Session, job_id: int) -> Optional[BenchmarkJob]:
        return db.query(BenchmarkJob).filter(BenchmarkJob.id == job_id).first()

    @staticmethod
    def list_jobs(
        db: Session,
        *,
        model_version_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[BenchmarkJob]:
        query = db.query(BenchmarkJob)
        if model_version_id is not None:
            query = query.filter(BenchmarkJob.model_version_id == model_version_id)
        return query.order_by(BenchmarkJob.created_at.desc()).limit(limit).all()

    @staticmethod
    def delete_job(db: Session, job_id: int) -> bool:
        job = db.query(BenchmarkJob).filter(BenchmarkJob.id == job_id).first()
        if not job:
            return False
        db.delete(job)
        db.commit()
        return True

    @staticmethod
    def execute_job(db: Session, job_id: int) -> None:
        """Run the benchmark for `job_id` (called from a Celery worker)."""
        job = db.query(BenchmarkJob).filter(BenchmarkJob.id == job_id).first()
        if not job:
            return

        job.status = BenchmarkJobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.error_message = None
        db.commit()

        try:
            version = (
                db.query(ModelVersion)
                .filter(ModelVersion.id == job.model_version_id)
                .first()
            )
            if not version:
                raise RuntimeError("Model version not found")

            model = db.query(Model).filter(Model.id == version.model_id).first()
            if not model:
                raise RuntimeError("Model not found")

            local_path = version.weights_path or None
            model_id = None
            if version.model_metadata and isinstance(version.model_metadata, dict):
                model_id = version.model_metadata.get("hf_model_id")
            if not model_id and model.source and model.source.startswith("hf:"):
                model_id = model.source.replace("hf:", "", 1)

            if not model_id and not local_path:
                raise RuntimeError(
                    "No local weights_path or hf_model_id found for this version or model source"
                )

            result = calculate_wikitext_benchmark_metrics(
                model_id=model_id,
                dataset_id=job.dataset_id,
                local_path=local_path,
                sample_count=job.sample_count,
                max_new_tokens=job.max_new_tokens,
                temperature=job.temperature,
                num_beams=job.num_beams,
                max_tokens=job.max_tokens,
                top_k=job.top_k,
                rare_percentile=job.rare_percentile,
                seed=job.seed,
            )

            now = datetime.utcnow()
            snapshot = AggregatedMetric(
                model_version_id=job.model_version_id,
                period_start=now,
                period_end=now,
                total_prompts=result.get("prompts_used", 0),
                avg_entropy=result.get("entropy"),
                avg_kl_divergence=None,
                avg_generation_time=None,
                avg_output_length=None,
                anomaly_count=0,
                anomaly_percentage=0.0,
                metrics_data={"benchmark": result, "benchmark_job_id": job.id},
            )
            db.add(snapshot)
            db.flush()

            job.result = result
            job.aggregated_metric_id = snapshot.id
            job.status = BenchmarkJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            # re-fetch in a clean transaction so we can persist the failure
            job = db.query(BenchmarkJob).filter(BenchmarkJob.id == job_id).first()
            if job:
                job.status = BenchmarkJobStatus.FAILED
                job.error_message = f"{exc.__class__.__name__}: {exc}"
                job.completed_at = datetime.utcnow()
                db.commit()
