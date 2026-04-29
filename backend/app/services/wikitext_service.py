from __future__ import annotations

import math
import re
import os
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
import torch
from huggingface_hub import model_info
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.services.metrics_calculator import MetricsCalculator
from app.core.config import get_settings

WIKITEXT_TRAIN_URL = (
    "https://huggingface.co/datasets/Salesforce/wikitext/resolve/main/"
    "wikitext-2-raw-v1/train-00000-of-00001.parquet?download=true"
)
DATA_DIR = Path("./data")
PARQUET_PATH = DATA_DIR / "wikitext-2-raw-v1-train.parquet"
CUSTOM_DATASET_DIR = DATA_DIR / "datasets"
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")
TOKENIZER_CACHE_DIR = DATA_DIR / "hf"
MODEL_CACHE_DIR = DATA_DIR / "hf"
DEFAULT_DATASET_ID = "wikitext-2"
DEFAULT_DATASET_LABEL = "WikiText-2 (raw)"
SUPPORTED_UPLOAD_EXTENSIONS = {".txt", ".csv", ".parquet", ".jsonl", ".json"}
MAX_REMOTE_MODEL_SIZE_BYTES = 5 * 1024 * 1024 * 1024
MAX_REMOTE_WEIGHT_SHARDS = 2


def _ensure_dataset() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PARQUET_PATH.exists():
        urlretrieve(WIKITEXT_TRAIN_URL, PARQUET_PATH)
    return PARQUET_PATH


def _sanitize_dataset_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if not safe_name:
        raise ValueError("Invalid dataset filename")
    return safe_name


def list_available_datasets() -> List[Dict[str, str]]:
    CUSTOM_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    datasets: List[Dict[str, str]] = [{"id": DEFAULT_DATASET_ID, "label": DEFAULT_DATASET_LABEL}]
    for file_path in sorted(CUSTOM_DATASET_DIR.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_UPLOAD_EXTENSIONS:
            continue
        datasets.append(
            {
                "id": f"custom:{file_path.name}",
                "label": f"Custom: {file_path.name}",
            }
        )
    return datasets


def store_custom_dataset(filename: str, content: bytes) -> Dict[str, str]:
    CUSTOM_DATASET_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_dataset_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(
            f"Unsupported dataset format '{suffix}'. Supported: {', '.join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))}"
        )

    target = CUSTOM_DATASET_DIR / safe_name
    target.write_bytes(content)
    return {"id": f"custom:{safe_name}", "label": f"Custom: {safe_name}"}


def _iter_tokens(text_rows: List[str], max_tokens: int) -> List[str]:
    tokens: List[str] = []
    for line in text_rows:
        line = (line or "").strip()
        if not line or line.startswith("="):
            continue
        for token in TOKEN_RE.findall(line):
            tokens.append(token)
            if len(tokens) >= max_tokens:
                return tokens
    return tokens


def _load_custom_dataset_rows(custom_file: Path) -> List[str]:
    suffix = custom_file.suffix.lower()

    if suffix == ".txt":
        return custom_file.read_text(encoding="utf-8", errors="ignore").splitlines()

    if suffix in {".csv", ".parquet"}:
        frame = pd.read_parquet(custom_file) if suffix == ".parquet" else pd.read_csv(custom_file)
        if frame.empty:
            return []
        if "text" in frame.columns:
            return frame["text"].dropna().astype(str).tolist()

        for col in frame.columns:
            series = frame[col]
            if series.dtype == "object":
                return series.dropna().astype(str).tolist()
        return frame.iloc[:, 0].dropna().astype(str).tolist()

    if suffix == ".jsonl":
        rows: List[str] = []
        for line in custom_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                text = data.get("text")
                if text is not None:
                    rows.append(str(text))
            elif isinstance(data, str):
                rows.append(data)
        return rows

    if suffix == ".json":
        parsed = json.loads(custom_file.read_text(encoding="utf-8", errors="ignore"))
        rows: List[str] = []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict) and item.get("text") is not None:
                    rows.append(str(item["text"]))
                elif isinstance(item, str):
                    rows.append(item)
        elif isinstance(parsed, dict) and isinstance(parsed.get("text"), list):
            rows = [str(v) for v in parsed["text"]]
        return rows

    raise ValueError(f"Unsupported dataset format '{suffix}'")


@lru_cache(maxsize=4)
def _load_tokenizer(model_id: str):
    TOKENIZER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    hf_token = get_settings().HUGGINGFACE_HUB_TOKEN or None
    if hf_token:
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", hf_token)
        os.environ.setdefault("HF_TOKEN", hf_token)
    return AutoTokenizer.from_pretrained(
        model_id,
        cache_dir=TOKENIZER_CACHE_DIR,
        use_fast=False,
        trust_remote_code=True,
        token=hf_token,
    )


@lru_cache(maxsize=2)
def _load_model_and_tokenizer(
    model_id: Optional[str],
    local_path: Optional[str] = None,
) -> Tuple[AutoTokenizer, AutoModelForCausalLM]:
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    hf_token = get_settings().HUGGINGFACE_HUB_TOKEN or None
    if hf_token:
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", hf_token)
        os.environ.setdefault("HF_TOKEN", hf_token)

    source = local_path or model_id
    if not source:
        raise ValueError("model_id or local_path must be provided")

    if local_path:
        normalized_local_path = Path(local_path).expanduser()
        if not normalized_local_path.exists():
            raise ValueError(f"Local model path does not exist: {local_path}")
        source = str(normalized_local_path)

    if model_id and not local_path:
        _validate_remote_model_feasibility(model_id, hf_token)

    use_hf = local_path is None
    cache_dir = MODEL_CACHE_DIR if use_hf else None
    token = hf_token if use_hf else None

    try:
        tokenizer = AutoTokenizer.from_pretrained(
            source,
            cache_dir=cache_dir,
            use_fast=False,
            trust_remote_code=True,
            token=token,
        )
        model = AutoModelForCausalLM.from_pretrained(
            source,
            cache_dir=cache_dir,
            torch_dtype=torch.float32,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            token=token,
        )
    except Exception as exc:
        source_type = "local_path" if local_path else "model_id"
        raise RuntimeError(f"Failed to load model from {source_type} '{source}': {exc}") from exc
    model.eval()
    return tokenizer, model


def _validate_remote_model_feasibility(model_id: str, hf_token: Optional[str]) -> None:
    """Reject very large remote models that are likely to timeout in this API path."""
    settings = get_settings()
    max_remote_weight_shards = max(1, int(settings.BENCHMARK_MAX_REMOTE_WEIGHT_SHARDS))
    max_remote_model_size_bytes = max(1, int(settings.BENCHMARK_MAX_REMOTE_MODEL_SIZE_GB)) * 1024 * 1024 * 1024

    try:
        info = model_info(model_id, token=hf_token)
    except Exception:
        return

    siblings = getattr(info, "siblings", []) or []
    weight_files = [
        item
        for item in siblings
        if getattr(item, "rfilename", "").endswith((".safetensors", ".bin"))
    ]
    shard_count = len(weight_files)
    total_size = 0
    for item in weight_files:
        size = getattr(item, "size", None)
        if isinstance(size, int):
            total_size += size

    if shard_count > max_remote_weight_shards or total_size > max_remote_model_size_bytes:
        size_gb = total_size / (1024 ** 3) if total_size > 0 else None
        size_hint = f", total weights ~{size_gb:.1f} GB" if size_gb is not None else ""
        raise ValueError(
            "Selected HF model is too large for synchronous benchmark requests in this deployment "
            f"(shards={shard_count}{size_hint}, limits: max_shards={max_remote_weight_shards}, "
            f"max_size_gb={int(settings.BENCHMARK_MAX_REMOTE_MODEL_SIZE_GB)}). "
            "Use a smaller model, a local quantized model via weights_path, "
            "or run pre-download/inference outside the API container."
        )


def _iter_tokens_with_tokenizer(text_rows: List[str], max_tokens: int, model_id: str) -> List[str]:
    tokenizer = _load_tokenizer(model_id)
    tokens: List[str] = []
    for line in text_rows:
        line = (line or "").strip()
        if not line or line.startswith("="):
            continue
        line_tokens = tokenizer.tokenize(line)
        for token in line_tokens:
            tokens.append(token)
            if len(tokens) >= max_tokens:
                return tokens
    return tokens


def _load_wikitext_rows() -> List[str]:
    parquet_path = _ensure_dataset()
    frame = pd.read_parquet(parquet_path)
    if "text" not in frame.columns:
        raise ValueError("WikiText-2 parquet missing 'text' column")
    return frame["text"].tolist()


def _load_dataset_rows(dataset_id: str) -> Tuple[str, List[str]]:
    dataset_id = (dataset_id or DEFAULT_DATASET_ID).strip()
    if not dataset_id or dataset_id == DEFAULT_DATASET_ID:
        return DEFAULT_DATASET_LABEL, _load_wikitext_rows()

    if not dataset_id.startswith("custom:"):
        raise ValueError("Unknown dataset_id. Use 'wikitext-2' or 'custom:<filename>'")

    safe_name = _sanitize_dataset_filename(dataset_id.split(":", 1)[1])
    custom_path = CUSTOM_DATASET_DIR / safe_name
    if not custom_path.exists() or not custom_path.is_file():
        raise ValueError(f"Custom dataset '{safe_name}' not found")

    return f"Custom: {safe_name}", _load_custom_dataset_rows(custom_path)


def _counter_to_probs(counter: Counter) -> Dict[str, float]:
    total = sum(counter.values())
    if total <= 0:
        return {}
    return {token: count / total for token, count in counter.items()}


def _js_divergence_from_counters(left: Counter, right: Counter) -> float:
    left_probs = _counter_to_probs(left)
    right_probs = _counter_to_probs(right)
    if not left_probs or not right_probs:
        return 0.0

    keys = sorted(set(left_probs.keys()) | set(right_probs.keys()))
    left_dist = [left_probs.get(k, 0.0) for k in keys]
    right_dist = [right_probs.get(k, 0.0) for k in keys]
    return MetricsCalculator.calculate_js_divergence(left_dist, right_dist)


def _format_token_for_display(tokenizer, token: str) -> str:
    """Convert raw tokenizer token (e.g., 'Ġthe', 'Ċ') into readable text markers."""
    try:
        rendered = tokenizer.convert_tokens_to_string([token])
    except Exception:
        rendered = token

    if rendered == "\n":
        return "[NL]"
    if rendered == "\t":
        return "[TAB]"
    if rendered and rendered.isspace():
        return f"[WSx{len(rendered)}]"

    if rendered and rendered.startswith(" "):
        space_count = len(rendered) - len(rendered.lstrip(" "))
        suffix = rendered.lstrip(" ")
        prefix = f"[SPx{space_count}]" if space_count > 1 else "[SP]"
        return f"{prefix}{suffix}" if suffix else prefix

    return rendered if rendered else token


def calculate_wikitext_benchmark_metrics(
    model_id: Optional[str],
    dataset_id: str = DEFAULT_DATASET_ID,
    sample_count: int = 8,
    max_new_tokens: int = 32,
    temperature: float = 0.7,
    num_beams: int = 1,
    max_tokens: int = 8000,
    top_k: int = 20,
    rare_percentile: float = 0.1,
    local_path: Optional[str] = None,
    seed: Optional[int] = None,
) -> Dict[str, object]:
    dataset_label, text_rows = _load_dataset_rows(dataset_id)
    if not text_rows:
        raise ValueError("Selected dataset is empty")

    rng = np.random.default_rng(seed)
    candidates = [row for row in text_rows if row and not row.startswith("=")]
    if not candidates:
        raise ValueError("Selected dataset has no usable rows")

    sample_count = min(sample_count, len(candidates))
    sampled_rows = rng.choice(candidates, size=sample_count, replace=False)

    tokenizer, model = _load_model_and_tokenizer(model_id, local_path)
    tokens: List[str] = []
    reference_tokens: List[str] = []
    sequence_perplexities: List[float] = []
    prompts_used = 0

    for prompt in sampled_rows:
        if len(tokens) >= max_tokens:
            break
        prompts_used += 1
        inputs = tokenizer(prompt, return_tensors="pt")
        prompt_ref_tokens = tokenizer.tokenize(prompt)
        for token in prompt_ref_tokens:
            reference_tokens.append(token)
            if len(reference_tokens) >= max_tokens:
                break

        input_len = inputs["input_ids"].shape[1]
        do_sample = num_beams <= 1 and temperature > 0
        generation_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "num_beams": num_beams,
            "pad_token_id": tokenizer.eos_token_id,
        }
        if do_sample:
            generation_kwargs["temperature"] = temperature
        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                **generation_kwargs,
            )

        generated_ids = outputs[0][input_len:]
        gen_tokens = tokenizer.convert_ids_to_tokens(generated_ids.tolist())

        if generated_ids.numel() > 0:
            full_ids = outputs[0].unsqueeze(0)
            labels = full_ids.clone()
            labels[:, :input_len] = -100
            with torch.inference_mode():
                loss = model(input_ids=full_ids, labels=labels).loss
            if loss is not None:
                sequence_perplexities.append(float(torch.exp(loss).item()))

        for token in gen_tokens:
            tokens.append(token)
            if len(tokens) >= max_tokens:
                break

    if not tokens:
        return {
            "dataset": dataset_label,
            "dataset_id": dataset_id,
            "tokenization": "model",
            "tokenizer_model_id": model_id,
            "model_id": model_id,
            "local_path": local_path,
            "sample_count": sample_count,
            "prompts_used": prompts_used,
            "num_beams": num_beams,
            "token_count": 0,
            "vocab_size": 0,
            "entropy": 0.0,
            "perplexity": 0.0,
            "avg_sequence_perplexity": 0.0,
            "std_sequence_perplexity": 0.0,
            "reference_entropy": 0.0,
            "reference_perplexity": 0.0,
            "js_divergence": 0.0,
            "rare_token_percentage": 0.0,
            "top_tokens": [],
        }

    counter = Counter(tokens)
    token_count = len(tokens)
    vocab_size = len(counter)

    probs = [count / token_count for count in counter.values()]
    entropy = MetricsCalculator.calculate_entropy(probs)
    perplexity = float(math.pow(2, entropy)) if entropy > 0 else 0.0

    ref_counter = Counter(reference_tokens)
    ref_token_count = len(reference_tokens)
    ref_probs = [count / ref_token_count for count in ref_counter.values()] if ref_token_count else []
    reference_entropy = MetricsCalculator.calculate_entropy(ref_probs) if ref_probs else 0.0
    reference_perplexity = float(math.pow(2, reference_entropy)) if reference_entropy > 0 else 0.0
    js_divergence = _js_divergence_from_counters(counter, ref_counter)
    avg_sequence_perplexity = float(np.mean(sequence_perplexities)) if sequence_perplexities else 0.0
    std_sequence_perplexity = float(np.std(sequence_perplexities)) if sequence_perplexities else 0.0

    counts = list(counter.values())
    threshold = np.percentile(counts, rare_percentile * 100) if counts else 0
    rare_count = sum(count for count in counts if count <= threshold)
    rare_token_percentage = (rare_count / token_count) * 100 if token_count else 0.0

    top_tokens = [
        {
            "token": _format_token_for_display(tokenizer, token),
            "count": count,
            "frequency": count / token_count,
        }
        for token, count in counter.most_common(top_k)
    ]

    return {
        "dataset": dataset_label,
        "dataset_id": dataset_id,
        "tokenization": "model",
        "tokenizer_model_id": model_id,
        "model_id": model_id,
        "sample_count": sample_count,
        "prompts_used": prompts_used,
        "num_beams": num_beams,
        "token_count": token_count,
        "vocab_size": vocab_size,
        "entropy": entropy,
        "perplexity": perplexity,
        "avg_sequence_perplexity": avg_sequence_perplexity,
        "std_sequence_perplexity": std_sequence_perplexity,
        "reference_entropy": reference_entropy,
        "reference_perplexity": reference_perplexity,
        "js_divergence": js_divergence,
        "rare_token_percentage": rare_token_percentage,
        "top_tokens": top_tokens,
    }
