from celery import Celery
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.evaluation_service import EvaluationService
from app.services.benchmark_job_service import BenchmarkJobService

settings = get_settings()

celery_app = Celery(
    "llm_collapse_detector",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)


@celery_app.task(name="app.tasks.run_evaluation_job")
def run_evaluation_job(job_id: int):
    """Execute prompt-set evaluation for a model version."""
    db = SessionLocal()
    try:
        EvaluationService.run_job(db, job_id)
    finally:
        db.close()


@celery_app.task(name="app.tasks.run_benchmark_job")
def run_benchmark_job(job_id: int):
    """Execute a WikiText / custom dataset benchmark in the background."""
    db = SessionLocal()
    try:
        BenchmarkJobService.execute_job(db, job_id)
    finally:
        db.close()
