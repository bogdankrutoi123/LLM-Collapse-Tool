from __future__ import annotations

import csv
import io
import json
import math
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.database import (
    EvaluationItem,
    EvaluationJob,
    EvaluationJobStatus,
    ModelVersion,
    PromptSet,
    PromptSetItem,
)
from app.schemas.schemas import EvaluationJobCreate, PromptCreate
from app.services.model_service import ModelService, ModelVersionService
from app.services.prompt_service import PromptService
from app.services.wikitext_service import _load_model_and_tokenizer


class EvaluationService:
    """Service implementing prompt-set based batch evaluations."""

    @staticmethod
    def _extract_prompt_rows(filename: str, content: bytes) -> List[Dict[str, Any]]:
        suffix = Path(filename).suffix.lower()
        text = content.decode("utf-8", errors="ignore")

        if suffix == ".txt":
            rows = [line.strip() for line in text.splitlines() if line.strip()]
            return [{"input_text": row} for row in rows]

        if suffix == ".jsonl":
            rows: List[Dict[str, Any]] = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, str):
                    rows.append({"input_text": payload})
                elif isinstance(payload, dict):
                    rows.append(payload)
            return rows

        if suffix == ".json":
            payload = json.loads(text)
            rows: List[Dict[str, Any]] = []
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, str):
                        rows.append({"input_text": item})
                    elif isinstance(item, dict):
                        rows.append(item)
            return rows

        if suffix == ".csv":
            reader = csv.DictReader(io.StringIO(text))
            return [dict(row) for row in reader]

        raise ValueError("Unsupported prompt set format. Use .txt, .csv, .json, or .jsonl")

    @staticmethod
    def create_prompt_set_from_upload(
        db: Session,
        *,
        name: str,
        description: Optional[str],
        filename: str,
        content: bytes,
        created_by_id: Optional[int],
    ) -> Tuple[PromptSet, int, int]:
        safe_name = Path(filename).name
        if not safe_name:
            raise ValueError("Invalid uploaded filename")

        rows = EvaluationService._extract_prompt_rows(safe_name, content)
        if not rows:
            raise ValueError("Uploaded prompt set contains no rows")

        base_name = (name or "").strip() or Path(safe_name).stem
        final_name = base_name
        suffix = 1
        while db.query(PromptSet).filter(PromptSet.name == final_name).first():
            suffix += 1
            final_name = f"{base_name}-{suffix}"

        prompt_set = PromptSet(
            name=final_name,
            description=(description or "").strip() or None,
            source_filename=safe_name,
            created_by_id=created_by_id,
        )
        db.add(prompt_set)
        db.flush()

        accepted = 0
        skipped = 0
        for idx, row in enumerate(rows):
            candidate = None
            if isinstance(row, dict):
                for key in ("input_text", "prompt", "text"):
                    value = row.get(key)
                    if value:
                        candidate = str(value).strip()
                        break
                if candidate is None:
                    for value in row.values():
                        if value is not None and str(value).strip():
                            candidate = str(value).strip()
                            break
            if not candidate:
                skipped += 1
                continue
            item = PromptSetItem(
                prompt_set_id=prompt_set.id,
                position=idx,
                input_text=candidate,
                item_metadata={k: v for k, v in row.items() if k not in {"input_text", "prompt", "text"}},
            )
            db.add(item)
            accepted += 1

        if accepted == 0:
            db.rollback()
            raise ValueError("Uploaded prompt set has no valid prompt rows")

        db.commit()
        db.refresh(prompt_set)
        return prompt_set, accepted, skipped

    @staticmethod
    def create_job(
        db: Session,
        request: EvaluationJobCreate,
        created_by_id: Optional[int],
    ) -> EvaluationJob:
        settings = get_settings()
        prompt_set = db.query(PromptSet).filter(PromptSet.id == request.prompt_set_id).first()
        if not prompt_set:
            raise ValueError("Prompt set not found")

        version = ModelVersionService.get_version_by_id(db, request.model_version_id)
        if not version:
            raise ValueError("Model version not found")

        active = db.query(EvaluationJob).filter(
            EvaluationJob.model_version_id == request.model_version_id,
            EvaluationJob.status.in_([EvaluationJobStatus.QUEUED, EvaluationJobStatus.RUNNING]),
        ).first()
        if active:
            raise ValueError(
                f"Evaluation job #{active.id} is already queued/running for this model version"
            )

        prompt_count = db.query(PromptSetItem).filter(PromptSetItem.prompt_set_id == request.prompt_set_id).count()
        if prompt_count > settings.EVAL_MAX_PROMPTS_PER_JOB:
            raise ValueError(
                f"Prompt set too large ({prompt_count}). Maximum supported is {settings.EVAL_MAX_PROMPTS_PER_JOB}"
            )

        top_k = min(request.top_k_token_probs, settings.EVAL_MAX_TOP_K_TOKEN_PROBS)
        generation_params = {
            "max_new_tokens": request.max_new_tokens,
            "temperature": request.temperature,
            "num_beams": request.num_beams,
            "do_sample": request.do_sample,
        }

        job = EvaluationJob(
            prompt_set_id=request.prompt_set_id,
            model_version_id=request.model_version_id,
            reference_version_id=request.reference_version_id,
            created_by_id=created_by_id,
            status=EvaluationJobStatus.QUEUED,
            generation_params=generation_params,
            store_full_token_probs=request.store_full_token_probs,
            top_k_token_probs=top_k,
            total_prompts=prompt_count,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def _resolve_model_source(db: Session, model_version_id: int) -> Tuple[Optional[str], Optional[str]]:
        version = ModelVersionService.get_version_by_id(db, model_version_id)
        if not version:
            raise ValueError("Model version not found")

        model = ModelService.get_model_by_id(db, version.model_id)
        if not model:
            raise ValueError("Model not found")

        local_path = version.weights_path or None
        model_id = None
        if version.model_metadata and isinstance(version.model_metadata, dict):
            model_id = version.model_metadata.get("hf_model_id")
        if not model_id and model.source and model.source.startswith("hf:"):
            model_id = model.source.replace("hf:", "", 1)

        if not model_id and not local_path:
            raise ValueError("No local weights_path or hf_model_id found for selected model version")

        return model_id, local_path

    @staticmethod
    def _generate_with_trace(
        tokenizer,
        model,
        prompt: str,
        generation_params: Dict[str, Any],
        store_full_token_probs: bool,
        top_k_token_probs: int,
    ) -> Tuple[str, List[str], Dict[str, Any], float]:
        inputs = tokenizer(prompt, return_tensors="pt")
        start = time.perf_counter()
        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=int(generation_params.get("max_new_tokens", 64)),
                do_sample=bool(generation_params.get("do_sample", True)),
                temperature=float(generation_params.get("temperature", 0.7)),
                num_beams=int(generation_params.get("num_beams", 1)),
                return_dict_in_generate=True,
                output_scores=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        sequences = outputs.sequences[0]
        prompt_len = inputs["input_ids"].shape[1]
        generated_ids = sequences[prompt_len:]
        generated_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        tokens = tokenizer.convert_ids_to_tokens(generated_ids.tolist())

        selected_token_probs: List[float] = []
        top_k_per_step: List[Dict[str, Any]] = []

        for step_scores, token_id in zip(outputs.scores or [], generated_ids.tolist()):
            step_probs = torch.softmax(step_scores[0], dim=-1)
            selected_token_probs.append(float(step_probs[token_id].item()))
            if store_full_token_probs:
                k = min(max(1, top_k_token_probs), int(step_probs.shape[-1]))
                values, indices = torch.topk(step_probs, k=k)
                top_k_per_step.append(
                    {
                        "token_ids": indices.tolist(),
                        "probabilities": [float(v) for v in values.tolist()],
                    }
                )

        token_probabilities: Dict[str, Any] = {
            "probabilities": selected_token_probs,
            "tokens": tokens,
        }
        if store_full_token_probs:
            token_probabilities["top_k_per_step"] = top_k_per_step

        return generated_text, tokens, token_probabilities, elapsed_ms

    @staticmethod
    def _redis_client() -> Redis:
        settings = get_settings()
        return Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD or None,
            decode_responses=True,
        )

    @staticmethod
    def run_job(db: Session, job_id: int) -> EvaluationJob:
        settings = get_settings()
        job = db.query(EvaluationJob).filter(EvaluationJob.id == job_id).first()
        if not job:
            raise ValueError("Evaluation job not found")
        if job.status not in [EvaluationJobStatus.QUEUED, EvaluationJobStatus.RUNNING]:
            return job

        lock_key = f"eval:model_version:{job.model_version_id}"
        lock_val = str(job.id)
        client = EvaluationService._redis_client()
        acquired = client.set(lock_key, lock_val, nx=True, ex=settings.EVAL_MODEL_LOCK_TTL_SECONDS)
        if not acquired:
            job.status = EvaluationJobStatus.FAILED
            job.error_message = "Another evaluation is already running for this model version"
            job.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job

        try:
            job.status = EvaluationJobStatus.RUNNING
            job.started_at = datetime.utcnow()
            db.commit()

            model_id, local_path = EvaluationService._resolve_model_source(db, job.model_version_id)
            tokenizer, model = _load_model_and_tokenizer(model_id=model_id, local_path=local_path)

            prompt_items = db.query(PromptSetItem).filter(
                PromptSetItem.prompt_set_id == job.prompt_set_id
            ).order_by(PromptSetItem.position.asc()).all()

            success = 0
            failed = 0

            for item in prompt_items:
                try:
                    generated_text, tokens, token_probs, elapsed_ms = EvaluationService._generate_with_trace(
                        tokenizer,
                        model,
                        item.input_text,
                        job.generation_params or {},
                        job.store_full_token_probs,
                        job.top_k_token_probs,
                    )

                    db_prompt = PromptService.create_prompt(
                        db,
                        PromptCreate(
                            model_version_id=job.model_version_id,
                            input_text=item.input_text,
                            temperature=(job.generation_params or {}).get("temperature"),
                            max_new_tokens=(job.generation_params or {}).get("max_new_tokens"),
                        ),
                    )
                    db_prompt = PromptService.update_prompt_with_response(
                        db,
                        db_prompt.id,
                        generated_text,
                        tokens=tokens,
                        token_probabilities=token_probs,
                        generation_time_ms=elapsed_ms,
                    )
                    PromptService.calculate_and_store_metrics(db, db_prompt.id)

                    eval_item = EvaluationItem(
                        job_id=job.id,
                        prompt_set_item_id=item.id,
                        prompt_id=db_prompt.id,
                        model_version_id=job.model_version_id,
                        input_text=item.input_text,
                        output_text=generated_text,
                        tokens=tokens,
                        token_probabilities=token_probs,
                        generation_time_ms=elapsed_ms,
                        status="completed",
                        processed_at=datetime.utcnow(),
                    )
                    db.add(eval_item)
                    success += 1
                except Exception as exc:
                    eval_item = EvaluationItem(
                        job_id=job.id,
                        prompt_set_item_id=item.id,
                        model_version_id=job.model_version_id,
                        input_text=item.input_text,
                        status="failed",
                        error_message=str(exc),
                        processed_at=datetime.utcnow(),
                    )
                    db.add(eval_item)
                    failed += 1

                job.processed_prompts = success + failed
                job.successful_prompts = success
                job.failed_prompts = failed
                db.commit()

            if success == 0:
                job.status = EvaluationJobStatus.FAILED
                if not job.error_message:
                    job.error_message = "No prompt runs completed successfully"
            elif failed > 0:
                job.status = EvaluationJobStatus.PARTIAL
            else:
                job.status = EvaluationJobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job
        except Exception as exc:
            job.status = EvaluationJobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db.commit()
            db.refresh(job)
            return job
        finally:
            try:
                current = client.get(lock_key)
                if current == lock_val:
                    client.delete(lock_key)
            except Exception:
                pass

    @staticmethod
    def _entropy_from_tokens(tokens: List[str]) -> Optional[float]:
        if not tokens:
            return None
        counter = Counter(tokens)
        total = sum(counter.values())
        if total <= 0:
            return None
        probs = [count / total for count in counter.values()]
        return -sum(p * math.log2(p) for p in probs if p > 0)

    @staticmethod
    def _metrics_for_job(db: Session, job: EvaluationJob) -> Dict[str, Optional[float]]:
        items = db.query(EvaluationItem).filter(
            EvaluationItem.job_id == job.id,
            EvaluationItem.status == "completed",
        ).all()

        if not items:
            return {
                "success_rate": 0.0,
                "avg_output_length": None,
                "avg_generation_time_ms": None,
                "entropy": None,
                "avg_selected_token_probability": None,
            }

        output_lengths = [len(i.output_text or "") for i in items if i.output_text is not None]
        generation_times = [i.generation_time_ms for i in items if i.generation_time_ms is not None]

        all_tokens: List[str] = []
        selected_probs: List[float] = []
        for item in items:
            if item.tokens:
                all_tokens.extend([str(tok) for tok in item.tokens])
            elif item.output_text:
                all_tokens.extend(item.output_text.split())
            probs = (item.token_probabilities or {}).get("probabilities", [])
            selected_probs.extend([float(p) for p in probs if p is not None])

        success_rate = (job.successful_prompts / job.total_prompts) * 100.0 if job.total_prompts else 0.0

        def _mean_or_none(values: List[float]) -> Optional[float]:
            return float(sum(values) / len(values)) if values else None

        return {
            "success_rate": success_rate,
            "avg_output_length": _mean_or_none([float(v) for v in output_lengths]),
            "avg_generation_time_ms": _mean_or_none([float(v) for v in generation_times]),
            "entropy": EvaluationService._entropy_from_tokens(all_tokens),
            "avg_selected_token_probability": _mean_or_none(selected_probs),
        }

    @staticmethod
    def compare_jobs(db: Session, job_id_1: int, job_id_2: int) -> Dict[str, Any]:
        job1 = db.query(EvaluationJob).filter(EvaluationJob.id == job_id_1).first()
        job2 = db.query(EvaluationJob).filter(EvaluationJob.id == job_id_2).first()
        if not job1 or not job2:
            raise ValueError("One or both jobs not found")

        if job1.status not in [EvaluationJobStatus.COMPLETED, EvaluationJobStatus.PARTIAL]:
            raise ValueError(f"Job #{job1.id} is not completed")
        if job2.status not in [EvaluationJobStatus.COMPLETED, EvaluationJobStatus.PARTIAL]:
            raise ValueError(f"Job #{job2.id} is not completed")

        m1 = EvaluationService._metrics_for_job(db, job1)
        m2 = EvaluationService._metrics_for_job(db, job2)

        deltas: Dict[str, Optional[float]] = {}
        for key, value1 in m1.items():
            value2 = m2.get(key)
            if value1 is None or value2 is None:
                deltas[key] = None
            else:
                deltas[key] = float(value2 - value1)

        return {
            "job_id_1": job1.id,
            "job_id_2": job2.id,
            "metrics_job_1": m1,
            "metrics_job_2": m2,
            "deltas": deltas,
        }
