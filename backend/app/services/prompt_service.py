from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import numpy as np
from scipy.stats import entropy as scipy_entropy
from app.models.database import Prompt, PromptMetric
from app.schemas.schemas import PromptCreate
from app.services.metrics_calculator import MetricsCalculator
from app.services.notification_service import AlertThresholdService
from app.services.model_service import ModelVersionService


def _extract_probs_vector(token_probabilities: dict) -> List[float]:
    """
    Return a flat probability list from token_probabilities, regardless of storage format.

    Handles two shapes:
      Legacy : {"probabilities": [0.12, 0.08, ...]}
      Per-pos: {"0": {"▁the": 0.42, "▁a": 0.18, ...}, "1": {...}, ...}

    For the per-position format the *max* probability at each step is returned,
    giving a sequence whose entropy/divergence reflects generation confidence.
    """
    if not token_probabilities:
        return []
    if "probabilities" in token_probabilities:
        val = token_probabilities["probabilities"]
        if isinstance(val, list):
            return [float(p) for p in val if isinstance(p, (int, float))]
    try:
        sorted_keys = sorted(token_probabilities.keys(), key=lambda k: int(k))
    except (ValueError, TypeError):
        return []
    result = []
    for key in sorted_keys:
        dist = token_probabilities[key]
        if isinstance(dist, dict) and dist:
            result.append(float(max(dist.values())))
        elif isinstance(dist, (int, float)):
            result.append(float(dist))
    return result


def _calculate_entropy(token_probabilities: dict) -> Optional[float]:
    """
    Calculate mean per-position Shannon entropy.

    For the per-position top-k format, entropy is computed per step (over the
    normalised top-k distribution) and then averaged, which gives the mean
    uncertainty per generation step — a meaningful collapse signal.
    For the legacy flat-list format the overall entropy is returned as before.
    """
    if not token_probabilities:
        return None
    if "probabilities" in token_probabilities:
        probs = token_probabilities.get("probabilities") or []
        return MetricsCalculator.calculate_entropy(probs) if probs else None
    try:
        sorted_keys = sorted(token_probabilities.keys(), key=lambda k: int(k))
    except (ValueError, TypeError):
        return None
    entropies = []
    for key in sorted_keys:
        dist = token_probabilities[key]
        if isinstance(dist, dict) and dist:
            probs = list(dist.values())
            total = sum(probs)
            if total > 0:
                norm = [p / total for p in probs]
                entropies.append(float(scipy_entropy(norm, base=2)))
    return float(np.mean(entropies)) if entropies else None


class PromptService:
    """Service for prompt and response management."""
    
    @staticmethod
    def get_prompt_by_id(db: Session, prompt_id: int) -> Optional[Prompt]:
        """Get prompt by ID."""
        return db.query(Prompt).filter(Prompt.id == prompt_id).first()
    
    @staticmethod
    def get_prompts(
        db: Session,
        skip: int = 0,
        limit: int = 100,
        model_version_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Prompt]:
        """Get list of prompts with filters."""
        query = db.query(Prompt)
        
        if model_version_id:
            query = query.filter(Prompt.model_version_id == model_version_id)
        if date_from:
            query = query.filter(Prompt.submitted_at >= date_from)
        if date_to:
            query = query.filter(Prompt.submitted_at <= date_to)
        
        return query.order_by(Prompt.submitted_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def create_prompt(db: Session, prompt: PromptCreate) -> Prompt:
        """Create new prompt."""
        db_prompt = Prompt(
            model_version_id=prompt.model_version_id,
            input_text=prompt.input_text,
            temperature=prompt.temperature,
            top_k=prompt.top_k,
            top_p=prompt.top_p,
            max_new_tokens=prompt.max_new_tokens,
            input_length=len(prompt.input_text)
        )
        db.add(db_prompt)
        db.commit()
        db.refresh(db_prompt)
        return db_prompt
    
    @staticmethod
    def update_prompt_with_response(
        db: Session,
        prompt_id: int,
        output_text: str,
        tokens: Optional[List[str]] = None,
        token_probabilities: Optional[dict] = None,
        logits: Optional[dict] = None,
        generation_time_ms: Optional[float] = None,
        cpu_time_ms: Optional[float] = None,
        gpu_time_ms: Optional[float] = None,
        generation_trace: Optional[dict] = None,
        embeddings: Optional[List] = None
    ) -> Optional[Prompt]:
        """Update prompt with model response."""
        db_prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not db_prompt:
            return None
        
        db_prompt.output_text = output_text
        db_prompt.output_length = len(output_text)
        db_prompt.tokens = tokens
        db_prompt.token_probabilities = token_probabilities
        db_prompt.logits = logits
        db_prompt.generation_time_ms = generation_time_ms
        db_prompt.cpu_time_ms = cpu_time_ms
        db_prompt.gpu_time_ms = gpu_time_ms
        db_prompt.generation_trace = generation_trace
        db_prompt.embeddings = embeddings
        db_prompt.processed_at = datetime.utcnow()
        
        db.commit()
        db.refresh(db_prompt)
        return db_prompt
    
    @staticmethod
    def delete_prompt(db: Session, prompt_id: int) -> bool:
        """Delete prompt."""
        db_prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
        if not db_prompt:
            return False
        
        db.delete(db_prompt)
        db.commit()
        return True
    
    @staticmethod
    def calculate_and_store_metrics(
        db: Session,
        prompt_id: int,
        reference_version_id: Optional[int] = None,
        baseline_type: str = "previous",
        baseline_days: Optional[int] = None,
        baseline_prompt_limit: int = 100
    ) -> Optional[PromptMetric]:
        """Calculate and store metrics for a prompt."""
        prompt = PromptService.get_prompt_by_id(db, prompt_id)
        if not prompt or not prompt.tokens or not prompt.token_probabilities:
            return None
        
        calculator = MetricsCalculator()

        entropy = _calculate_entropy(prompt.token_probabilities)
        probs = _extract_probs_vector(prompt.token_probabilities)

        token_frequency = calculator.calculate_token_frequency(prompt.tokens)
        
        baseline_metadata = {
            "baseline_type": baseline_type,
            "reference_version_id": reference_version_id,
            "baseline_days": baseline_days,
            "baseline_prompt_limit": baseline_prompt_limit
        }

        resolved_reference_version_id = reference_version_id

        if baseline_type == "previous":
            version = ModelVersionService.get_version_by_id(db, prompt.model_version_id)
            if version and version.previous_version_id:
                resolved_reference_version_id = version.previous_version_id
        elif baseline_type == "current":
            resolved_reference_version_id = prompt.model_version_id

        ref_query = db.query(Prompt)
        if resolved_reference_version_id:
            ref_query = ref_query.filter(Prompt.model_version_id == resolved_reference_version_id)

        if baseline_days:
            from datetime import timedelta
            window_start = datetime.utcnow() - timedelta(days=baseline_days)
            ref_query = ref_query.filter(Prompt.submitted_at >= window_start)

        ref_prompts = ref_query.limit(baseline_prompt_limit).all()

        kl_divergence = None
        js_divergence = None
        wasserstein_distance = None
        ngram_drift = None
        embedding_drift = None
        rare_token_pct = None
        new_token_pct = None

        token_distribution_by_position = []
        if ref_prompts:
            ref_tokens = []
            for rp in ref_prompts:
                if rp.tokens:
                    ref_tokens.extend(rp.tokens)

            if ref_tokens:
                rare_token_pct = calculator.calculate_rare_token_percentage(
                    prompt.tokens, ref_tokens
                )
                new_token_pct = calculator.calculate_new_token_percentage(
                    prompt.tokens, ref_tokens
                )

                ngram_drift = calculator.calculate_ngram_drift(prompt.tokens, ref_tokens, n=2)
                token_distribution_by_position = calculator.calculate_token_distribution_by_position(
                    prompt.tokens, ref_tokens
                )

            if ref_prompts[0].token_probabilities:
                ref_probs = _extract_probs_vector(ref_prompts[0].token_probabilities)
                if ref_probs and probs:
                    kl_divergence = calculator.calculate_kl_divergence(probs, ref_probs)
                    js_divergence = calculator.calculate_js_divergence(probs, ref_probs)
                    wasserstein_distance = calculator.calculate_wasserstein_distance(probs, ref_probs)

            if prompt.embeddings:
                ref_embeddings = [rp.embeddings for rp in ref_prompts if rp.embeddings]
                if ref_embeddings:
                    embedding_drift = calculator.calculate_embedding_drift(prompt.embeddings, ref_embeddings)
        
        all_lengths = [p.output_length for p in db.query(Prompt).filter(
            Prompt.model_version_id == prompt.model_version_id,
            Prompt.output_length.isnot(None)
        ).all()]
        
        _, median_length, length_variance = calculator.calculate_length_statistics(all_lengths)
        
        db_metric = PromptMetric(
            prompt_id=prompt_id,
            entropy=entropy,
            kl_divergence=kl_divergence,
            js_divergence=js_divergence,
            wasserstein_distance=wasserstein_distance,
            ngram_drift=ngram_drift,
            embedding_drift=embedding_drift,
            token_frequency=token_frequency,
            token_distribution_by_position=token_distribution_by_position,
            rare_token_percentage=rare_token_pct,
            new_token_percentage=new_token_pct,
            median_length=median_length,
            length_variance=length_variance,
            baseline_metadata=baseline_metadata,
            is_anomaly=False,
            anomaly_reasons=[],
        )

        db.add(db_metric)
        db.commit()
        db.refresh(db_metric)

        fired = AlertThresholdService.evaluate_thresholds_for_metric(db, db_metric)
        if fired:
            db_metric.is_anomaly = True
            db_metric.anomaly_reasons = [n.title for n in fired]
            db.commit()

        return db_metric
    
    @staticmethod
    def get_prompt_metrics(db: Session, prompt_id: int) -> Optional[PromptMetric]:
        """Get metrics for a prompt."""
        return db.query(PromptMetric).filter(PromptMetric.prompt_id == prompt_id).first()
