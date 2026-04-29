from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import time
from app.db.session import get_db
from app.schemas.schemas import (
    PromptCreate, PromptResponse, BatchPromptCreate,
    PromptMetricResponse, PromptResponseUpdate
)
from app.services.prompt_service import PromptService
from app.services.model_service import ModelVersionService, ModelService
from app.api.dependencies import get_current_user
from app.models.database import User, Prompt
from app.services.audit_service import AuditService

router = APIRouter(prefix="/prompts", tags=["Prompts"])


def _load_model_and_tokenizer(model_id: str, local_path: str | None = None):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tokenizer = AutoTokenizer.from_pretrained(
        local_path or model_id, use_fast=True
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(local_path or model_id)
    return tokenizer, model.eval()


def _to_dict(obj):
    data = obj.__dict__.copy()
    data.pop("_sa_instance_state", None)
    return data


@router.get("/count")
def count_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {"count": db.query(Prompt).count()}


@router.get("/", response_model=List[PromptResponse])
def list_prompts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    model_version_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get list of prompts with filters."""
    prompts = PromptService.get_prompts(
        db,
        skip=skip,
        limit=limit,
        model_version_id=model_version_id,
        date_from=date_from,
        date_to=date_to
    )
    return prompts


@router.get("/{prompt_id}", response_model=PromptResponse)
def get_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get prompt by ID."""
    prompt = PromptService.get_prompt_by_id(db, prompt_id)
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found"
        )
    return prompt


@router.post("/", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
def create_prompt(
    prompt: PromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new prompt."""
    version = ModelVersionService.get_version_by_id(db, prompt.model_version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model version not found"
        )
    
    db_prompt = PromptService.create_prompt(db, prompt)
    AuditService.log(db, current_user.id, "create", "prompt", db_prompt.id, None, _to_dict(db_prompt))
    return db_prompt


@router.post("/batch", response_model=List[PromptResponse], status_code=status.HTTP_201_CREATED)
def create_prompts_batch(
    batch: BatchPromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create multiple prompts in batch."""
    db_prompts = []
    
    for prompt in batch.prompts:
        version = ModelVersionService.get_version_by_id(db, prompt.model_version_id)
        if not version:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Model version {prompt.model_version_id} not found"
            )
        
        db_prompt = PromptService.create_prompt(db, prompt)
        db_prompts.append(db_prompt)
        AuditService.log(db, current_user.id, "create", "prompt", db_prompt.id, None, _to_dict(db_prompt))
    
    return db_prompts


@router.put("/{prompt_id}/response", response_model=PromptResponse)
def update_prompt_response(
    prompt_id: int,
    output_text: Optional[str] = None,
    tokens: Optional[List[str]] = None,
    token_probabilities: Optional[dict] = None,
    logits: Optional[dict] = None,
    generation_time_ms: Optional[float] = None,
    cpu_time_ms: Optional[float] = None,
    gpu_time_ms: Optional[float] = None,
    generation_trace: Optional[dict] = None,
    embeddings: Optional[List] = None,
    payload: Optional[PromptResponseUpdate] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update prompt with model response."""
    existing = PromptService.get_prompt_by_id(db, prompt_id)
    old_value = _to_dict(existing) if existing else None
    if payload:
        data = payload.model_dump(exclude_unset=True)
    else:
        data = {
            "output_text": output_text,
            "tokens": tokens,
            "token_probabilities": token_probabilities,
            "logits": logits,
            "generation_time_ms": generation_time_ms,
            "cpu_time_ms": cpu_time_ms,
            "gpu_time_ms": gpu_time_ms,
            "generation_trace": generation_trace,
            "embeddings": embeddings,
        }

    if data.get("output_text") is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="output_text is required"
        )

    db_prompt = PromptService.update_prompt_with_response(
        db,
        prompt_id,
        data.get("output_text"),
        data.get("tokens"),
        data.get("token_probabilities"),
        data.get("logits"),
        data.get("generation_time_ms"),
        data.get("cpu_time_ms"),
        data.get("gpu_time_ms"),
        data.get("generation_trace"),
        data.get("embeddings"),
    )
    
    if not db_prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found"
        )

    existing_metric = PromptService.get_prompt_metrics(db, prompt_id)
    if not existing_metric:
        PromptService.calculate_and_store_metrics(db, prompt_id)

    AuditService.log(db, current_user.id, "update", "prompt", db_prompt.id, old_value, _to_dict(db_prompt))
    return db_prompt


@router.post("/{prompt_id}/generate", response_model=PromptResponse)
def generate_prompt_response(
    prompt_id: int,
    max_new_tokens: Optional[int] = Body(64, embed=True),
    temperature: Optional[float] = Body(0.7, embed=True),
    top_k: Optional[int] = Body(None, embed=True),
    top_p: Optional[float] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import torch

    prompt = PromptService.get_prompt_by_id(db, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

    version = ModelVersionService.get_version_by_id(db, prompt.model_version_id)
    model_obj = ModelService.get_model_by_id(db, version.model_id) if version else None

    model_id = None
    if version and version.model_metadata:
        model_id = version.model_metadata.get("hf_model_id")
    if not model_id and model_obj and model_obj.source:
        src = model_obj.source
        model_id = src[3:] if src.startswith("hf:") else src
    if not model_id and version:
        model_id = version.weights_path

    if not model_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No model source configured")

    tokenizer, model = _load_model_and_tokenizer(model_id, version.weights_path if version else None)

    gen_kwargs: dict = {"max_new_tokens": max_new_tokens or 64}
    if temperature is not None:
        gen_kwargs["temperature"] = temperature
        gen_kwargs["do_sample"] = temperature > 0
    if top_k is not None:
        gen_kwargs["top_k"] = top_k
    if top_p is not None:
        gen_kwargs["top_p"] = top_p

    inputs = tokenizer(prompt.input_text, return_tensors="pt")
    t0 = time.perf_counter()
    with torch.no_grad():
        out = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            **gen_kwargs,
            output_scores=True,
            return_dict_in_generate=True,
        )
    gen_ms = (time.perf_counter() - t0) * 1000.0

    input_len  = inputs["input_ids"].shape[1]
    new_tokens = out.sequences[0][input_len:]
    output_text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    token_list  = tokenizer.convert_ids_to_tokens(new_tokens.tolist())

    token_probs: dict = {}
    if hasattr(out, "scores") and out.scores:
        import torch.nn.functional as F
        for i, score in enumerate(out.scores):
            probs = F.softmax(score[0], dim=-1)
            top = torch.topk(probs, min(20, probs.shape[0]))
            token_probs[str(i)] = {
                tokenizer.convert_ids_to_tokens([idx.item()])[0]: round(p.item(), 6)
                for idx, p in zip(top.indices, top.values)
            }

    updated = PromptService.update_prompt_with_response(
        db, prompt_id,
        output_text=output_text,
        tokens=token_list,
        token_probabilities=token_probs,
        generation_time_ms=gen_ms,
    )
    if token_probs:
        PromptService.calculate_and_store_metrics(db, prompt_id)
    return updated


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a prompt."""
    existing = PromptService.get_prompt_by_id(db, prompt_id)
    if not PromptService.delete_prompt(db, prompt_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prompt not found"
        )
    AuditService.log(db, current_user.id, "delete", "prompt", prompt_id, _to_dict(existing) if existing else None, None)


@router.post("/{prompt_id}/metrics", response_model=PromptMetricResponse)
def calculate_prompt_metrics(
    prompt_id: int,
    reference_version_id: Optional[int] = None,
    baseline_type: str = Query("previous", pattern="^(previous|current|reference)$"),
    baseline_days: Optional[int] = Query(None, ge=1),
    baseline_prompt_limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Calculate and store metrics for a prompt."""
    metric = PromptService.calculate_and_store_metrics(
        db,
        prompt_id,
        reference_version_id,
        baseline_type=baseline_type if baseline_type != "reference" else "reference",
        baseline_days=baseline_days,
        baseline_prompt_limit=baseline_prompt_limit
    )
    
    if not metric:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not calculate metrics. Ensure prompt has output data."
        )
    AuditService.log(db, current_user.id, "create", "prompt_metric", metric.id, None, _to_dict(metric))
    return metric


@router.get("/{prompt_id}/metrics", response_model=PromptMetricResponse)
def get_prompt_metrics(
    prompt_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get metrics for a prompt."""
    metric = PromptService.get_prompt_metrics(db, prompt_id)
    if not metric:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Metrics not found for this prompt"
        )
    return metric
