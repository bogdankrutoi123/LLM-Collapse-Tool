from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from datetime import datetime
import numpy as np
from app.models.database import Prompt, PromptMetric, AggregatedMetric
from app.services.metrics_calculator import MetricsCalculator


class AnalyticsService:
    """Service for analytics, aggregation, and comparison."""

    @staticmethod
    def _compute_metrics_map_from_raw(
        db: Session,
        version_id: int
    ) -> Dict[str, Optional[float]]:
        """Compute metrics directly from prompt/prompt-metric data for a version."""
        prompts = db.query(Prompt).filter(Prompt.model_version_id == version_id).all()
        prompt_ids = [p.id for p in prompts]
        metrics = db.query(PromptMetric).filter(PromptMetric.prompt_id.in_(prompt_ids)).all() if prompt_ids else []

        entropies = [m.entropy for m in metrics if m.entropy is not None]
        kl_divergences = [m.kl_divergence for m in metrics if m.kl_divergence is not None]
        generation_times = [p.generation_time_ms for p in prompts if p.generation_time_ms is not None]
        output_lengths = [p.output_length for p in prompts if p.output_length is not None]
        anomaly_flags = [m.is_anomaly for m in metrics if m.is_anomaly is not None]

        def mean_or_none(values: List[float]) -> Optional[float]:
            return float(np.mean(values)) if values else None

        anomaly_percentage: Optional[float] = None
        if anomaly_flags:
            anomaly_percentage = (sum(1 for flag in anomaly_flags if flag) / len(anomaly_flags)) * 100.0

        return {
            "avg_entropy": mean_or_none(entropies),
            "avg_kl_divergence": mean_or_none(kl_divergences),
            "avg_generation_time": mean_or_none(generation_times),
            "avg_output_length": mean_or_none(output_lengths),
            "anomaly_percentage": anomaly_percentage,
        }

    @staticmethod
    def aggregate_metrics(
        db: Session,
        model_version_id: int,
        period_start: datetime,
        period_end: datetime
    ) -> AggregatedMetric:
        """Aggregate metrics for a model version and period."""
        prompts = db.query(Prompt).filter(
            Prompt.model_version_id == model_version_id,
            Prompt.submitted_at >= period_start,
            Prompt.submitted_at <= period_end
        ).all()

        prompt_ids = [p.id for p in prompts]
        metrics = db.query(PromptMetric).filter(PromptMetric.prompt_id.in_(prompt_ids)).all() if prompt_ids else []

        entropies = [m.entropy for m in metrics if m.entropy is not None]
        kl_divergences = [m.kl_divergence for m in metrics if m.kl_divergence is not None]
        generation_times = [p.generation_time_ms for p in prompts if p.generation_time_ms is not None]
        output_lengths = [p.output_length for p in prompts if p.output_length is not None]
        anomaly_flags = [m.is_anomaly for m in metrics if m.is_anomaly is not None]

        aggregated = MetricsCalculator.calculate_aggregated_metrics(
            entropies,
            kl_divergences,
            generation_times,
            output_lengths,
            anomaly_flags
        )

        db_metric = AggregatedMetric(
            model_version_id=model_version_id,
            period_start=period_start,
            period_end=period_end,
            total_prompts=aggregated.get("total_prompts", 0),
            avg_entropy=aggregated.get("avg_entropy"),
            avg_kl_divergence=aggregated.get("avg_kl_divergence"),
            avg_generation_time=aggregated.get("avg_generation_time"),
            avg_output_length=aggregated.get("avg_output_length"),
            anomaly_count=aggregated.get("anomaly_count", 0),
            anomaly_percentage=aggregated.get("anomaly_percentage", 0.0),
            metrics_data={"custom": aggregated}
        )
        db.add(db_metric)
        db.commit()
        db.refresh(db_metric)
        return db_metric

    @staticmethod
    def compare_versions(
        db: Session,
        version_id_1: int,
        version_id_2: int
    ) -> Dict[str, Dict[str, Optional[float]]]:
        """Compare basic metrics between two versions using latest aggregated record if available."""
        m1 = db.query(AggregatedMetric).filter(
            AggregatedMetric.model_version_id == version_id_1
        ).order_by(AggregatedMetric.calculated_at.desc()).first()
        m2 = db.query(AggregatedMetric).filter(
            AggregatedMetric.model_version_id == version_id_2
        ).order_by(AggregatedMetric.calculated_at.desc()).first()

        def metric_map(m: Optional[AggregatedMetric], version_id: int) -> Dict[str, Optional[float]]:
            if m and (m.total_prompts or 0) > 0:
                base = {
                    "avg_entropy": m.avg_entropy,
                    "avg_kl_divergence": m.avg_kl_divergence,
                    "avg_generation_time": m.avg_generation_time,
                    "avg_output_length": m.avg_output_length,
                    "anomaly_percentage": m.anomaly_percentage,
                }
                benchmark = (m.metrics_data or {}).get("benchmark", {})
                for key in ("perplexity", "js_divergence", "rare_token_percentage",
                            "vocab_size", "avg_sequence_perplexity"):
                    if key in benchmark and benchmark[key] is not None:
                        base[key] = float(benchmark[key])
                return base
            return AnalyticsService._compute_metrics_map_from_raw(db, version_id)

        return {
            "version_1": metric_map(m1, version_id_1),
            "version_2": metric_map(m2, version_id_2)
        }

    @staticmethod
    def generate_comparison_report(
        db: Session,
        version_id_1: int,
        version_id_2: int
    ) -> Dict[str, object]:
        comparison = AnalyticsService.compare_versions(db, version_id_1, version_id_2)
        v1 = comparison["version_1"]
        v2 = comparison["version_2"]

        changes = []
        for key in v1.keys():
            a = v1.get(key)
            b = v2.get(key)
            if a is None or b is None:
                continue
            delta = b - a
            pct = (delta / a * 100.0) if a != 0 else None
            highlight = False
            if pct is not None and abs(pct) >= 10:
                highlight = True
            if abs(delta) >= 0.1:
                highlight = True
            changes.append({
                "metric": key,
                "version_1": a,
                "version_2": b,
                "delta": delta,
                "percent_change": pct,
                "highlight": highlight
            })

        return {
            "version_1": v1,
            "version_2": v2,
            "changes": changes
        }
