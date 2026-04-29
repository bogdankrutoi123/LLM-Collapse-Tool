import os, random
os.environ.setdefault("DATABASE_URL", "postgresql://llm_user:llm_password@db:5432/llm_detector")
os.environ.setdefault("SECRET_KEY", "dev-secret-key")
os.environ.setdefault("BOOTSTRAP_ADMIN_TOKEN", "dev")

from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.database import Model, ModelVersion, AggregatedMetric, ModelStatus

random.seed(42)
engine  = create_engine(os.environ["DATABASE_URL"])
Session = sessionmaker(bind=engine)
db      = Session()


def ts(days_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def jitter(v: float, pct: float = 0.04) -> float:
    return round(v * (1 + random.uniform(-pct, pct)), 4)


def add_metric(version_id: int, days_ago: float, entropy: float, kl: float,
               gen_time: float, output_len: float, anomaly_pct: float, n: int = 120):
    start = ts(days_ago)
    db.add(AggregatedMetric(
        model_version_id    = version_id,
        period_start        = start,
        period_end          = start + timedelta(hours=6),
        total_prompts       = n,
        avg_entropy         = jitter(entropy),
        avg_kl_divergence   = jitter(kl, 0.08),
        avg_generation_time = jitter(gen_time, 0.06),
        avg_output_length   = jitter(output_len, 0.05),
        anomaly_count       = int(n * anomaly_pct / 100),
        anomaly_percentage  = round(anomaly_pct, 2),
        metrics_data        = {
            "benchmark": {
                "perplexity":              round(2 ** entropy, 2),
                "js_divergence":           round(kl * 0.55, 4),
                "rare_token_percentage":   round(2.1 + (5.0 - entropy) * 3.8, 2),
                "vocab_size":              50256,
                "avg_sequence_perplexity": round(2 ** entropy * 1.12, 2),
                "sample_count":            n,
                "prompts_used":            n,
            }
        }
    ))


def get_or_create_model(name, description, source, status):
    m = db.query(Model).filter(Model.name == name).first()
    if not m:
        m = Model(name=name, description=description, source=source, status=status)
        db.add(m); db.flush()
    return m


def get_or_create_version(model_id, version, description, days_ago, is_current, meta):
    v = db.query(ModelVersion).filter(
        ModelVersion.model_id == model_id,
        ModelVersion.version  == version
    ).first()
    if not v:
        v = ModelVersion(model_id=model_id, version=version, description=description,
                         deployment_date=ts(days_ago), is_current=is_current,
                         model_metadata=meta)
        db.add(v); db.flush()
    return v


m1 = get_or_create_model("GPT-2 Medium",
                          "OpenAI GPT-2 345M, fine-tuned on domain corpus",
                          "openai/gpt2-medium", ModelStatus.ACTIVE)

v1 = get_or_create_version(m1.id, "1.0.0", "Initial production deployment",
                            62, False, {"params": "345M", "context": 1024})
for i, d in enumerate(range(60, 50, -1)):
    add_metric(v1.id, d + random.uniform(-0.3, 0.3),
               entropy=4.28, kl=0.118, gen_time=122.0, output_len=87.0, anomaly_pct=1.2)

v2 = get_or_create_version(m1.id, "1.1.0", "Fine-tuned on Q3 user conversations",
                            45, False, {"params": "345M", "context": 1024, "finetune_steps": 5000})
for d in range(44, 34, -1):
    add_metric(v2.id, d + random.uniform(-0.3, 0.3),
               entropy=4.11, kl=0.154, gen_time=119.0, output_len=84.0, anomaly_pct=2.1)

v3 = get_or_create_version(m1.id, "1.2.0", "Extended fine-tuning — distribution shift suspected",
                            28, False, {"params": "345M", "context": 1024, "finetune_steps": 18000})
for d in range(27, 17, -1):
    add_metric(v3.id, d + random.uniform(-0.3, 0.3),
               entropy=3.47, kl=0.312, gen_time=128.0, output_len=74.0, anomaly_pct=7.8)

v4 = get_or_create_version(m1.id, "2.0.0", "Major retraining with expanded dataset",
                            10, True, {"params": "345M", "context": 1024, "finetune_steps": 45000})
for d in range(9, 1, -1):
    add_metric(v4.id, d + random.uniform(-0.2, 0.2),
               entropy=2.14, kl=0.683, gen_time=148.0, output_len=42.0,
               anomaly_pct=23.4, n=95)

m2 = get_or_create_model("LLaMA-7B",
                          "Meta LLaMA 7B instruction-following model",
                          "meta-llama/Llama-2-7b-hf", ModelStatus.ACTIVE)

lv1 = get_or_create_version(m2.id, "v1.0", "Base model checkpoint",
                             40, False, {"params": "7B", "context": 4096})
for d in range(39, 22, -2):
    add_metric(lv1.id, d, entropy=4.71, kl=0.094, gen_time=310.0, output_len=112.0, anomaly_pct=0.8)

lv2 = get_or_create_version(m2.id, "v1.5-instruct", "Instruction-tuned with RLHF",
                             14, True, {"params": "7B", "context": 4096, "rlhf": True})
for d in range(13, 1, -1):
    add_metric(lv2.id, d, entropy=4.02, kl=0.241, gen_time=298.0, output_len=98.0, anomaly_pct=5.3)

db.commit()

print("done")
for m in [m1, m2]:
    db.refresh(m)
    print(f"  {m.name} (id={m.id})")
    for v in db.query(ModelVersion).filter(ModelVersion.model_id == m.id).order_by(ModelVersion.id):
        n = db.query(AggregatedMetric).filter(AggregatedMetric.model_version_id == v.id).count()
        print(f"    {v.version:<22} id={v.id}  {n} periods")
