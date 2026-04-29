from celery import Celery
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.evaluation_service import EvaluationService

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
