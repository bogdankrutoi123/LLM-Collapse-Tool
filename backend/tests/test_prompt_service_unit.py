from __future__ import annotations

import pytest

from app.models.database import Model, ModelStatus, ModelVersion, Prompt, PromptMetric
from app.schemas.schemas import PromptCreate
from app.services.prompt_service import (
    PromptService,
    _calculate_entropy,
    _extract_probs_vector,
)


def _make_version(db, *, name: str = "unit-model") -> ModelVersion:
    model = Model(name=name, source="hf:test/unit", status=ModelStatus.ACTIVE)
    db.add(model)
    db.flush()
    version = ModelVersion(
        model_id=model.id,
        version="v1",
        model_metadata={"hf_model_id": "test/unit"},
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def _make_prompt(db, version_id: int, text: str = "Hello world") -> Prompt:
    return PromptService.create_prompt(
        db,
        PromptCreate(
            model_version_id=version_id,
            input_text=text,
            temperature=0.7,
            max_new_tokens=32,
        ),
    )


def test_extract_probs_legacy_format():
    result = _extract_probs_vector({"probabilities": [0.5, 0.3, 0.2]})
    assert result == pytest.approx([0.5, 0.3, 0.2])


def test_extract_probs_per_position_format():
    token_probs = {
        "0": {"tok_a": 0.7, "tok_b": 0.2},
        "1": {"tok_c": 0.9, "tok_d": 0.05},
    }
    result = _extract_probs_vector(token_probs)
    assert result == pytest.approx([0.7, 0.9])


def test_extract_probs_empty_dict_returns_empty():
    assert _extract_probs_vector({}) == []


def test_extract_probs_none_returns_empty():
    assert _extract_probs_vector(None) == []


def test_extract_probs_invalid_keys_returns_empty():
    result = _extract_probs_vector({"non_numeric": "value", "also_bad": "x"})
    assert result == []


def test_extract_probs_legacy_filters_non_numeric():
    result = _extract_probs_vector({"probabilities": [0.5, "bad", 0.3]})
    assert result == pytest.approx([0.5, 0.3])


def test_extract_probs_per_position_scalar_values():
    result = _extract_probs_vector({"0": 0.8, "1": 0.6})
    assert result == pytest.approx([0.8, 0.6])


def test_extract_probs_per_position_empty_dicts_skipped():
    result = _extract_probs_vector({"0": {}, "1": {"a": 0.9}})
    assert result == pytest.approx([0.9])


def test_calculate_entropy_legacy_format_uniform():
    entropy = _calculate_entropy({"probabilities": [0.5, 0.5]})
    assert entropy is not None
    assert entropy == pytest.approx(1.0, rel=1e-4)


def test_calculate_entropy_per_position_format():
    token_probs = {
        "0": {"tok_a": 0.5, "tok_b": 0.5},
        "1": {"tok_c": 0.5, "tok_d": 0.5},
    }
    entropy = _calculate_entropy(token_probs)
    assert entropy is not None
    assert entropy == pytest.approx(1.0, rel=1e-4)


def test_calculate_entropy_empty_returns_none():
    assert _calculate_entropy({}) is None


def test_calculate_entropy_none_returns_none():
    assert _calculate_entropy(None) is None


def test_calculate_entropy_legacy_empty_probs_list_returns_none():
    assert _calculate_entropy({"probabilities": []}) is None


def test_calculate_entropy_per_position_only_empty_dicts_returns_none():
    result = _calculate_entropy({"0": {}, "1": {}})
    assert result is None


def test_calculate_entropy_per_position_degenerate_distribution():
    entropy = _calculate_entropy({"0": {"tok_a": 1.0}})
    assert entropy is not None
    assert entropy == pytest.approx(0.0, abs=1e-6)


def test_create_prompt_persisted_with_correct_fields(db):
    version = _make_version(db)
    prompt = _make_prompt(db, version.id)
    assert prompt.id is not None
    assert prompt.input_text == "Hello world"
    assert prompt.input_length == len("Hello world")
    assert prompt.output_text is None
    assert prompt.tokens is None


def test_update_prompt_changes_input_clears_output(db):
    version = _make_version(db, name="upd-model-1")
    prompt = _make_prompt(db, version.id)

    prompt.output_text = "previous output"
    prompt.output_length = 15
    prompt.tokens = ["tok_1", "tok_2"]
    prompt.token_probabilities = {"0": {"tok_1": 0.9}}
    prompt.generation_time_ms = 100.0
    db.commit()

    updated = PromptService.update_prompt(db, prompt.id, input_text="New input text")

    assert updated.input_text == "New input text"
    assert updated.output_text is None
    assert updated.output_length is None
    assert updated.tokens is None
    assert updated.token_probabilities is None
    assert updated.generation_time_ms is None
    assert updated.processed_at is None


def test_update_prompt_same_input_preserves_output(db):
    version = _make_version(db, name="upd-model-2")
    prompt = _make_prompt(db, version.id)

    prompt.output_text = "some output"
    prompt.output_length = 11
    db.commit()

    updated = PromptService.update_prompt(db, prompt.id, input_text="Hello world")
    assert updated.output_text == "some output"


def test_update_prompt_temperature_only(db):
    version = _make_version(db, name="upd-model-3")
    prompt = _make_prompt(db, version.id)
    updated = PromptService.update_prompt(db, prompt.id, temperature=1.2)
    assert updated.temperature == pytest.approx(1.2)


def test_update_prompt_top_k_and_top_p(db):
    version = _make_version(db, name="upd-model-4")
    prompt = _make_prompt(db, version.id)
    updated = PromptService.update_prompt(db, prompt.id, top_k=50, top_p=0.9)
    assert updated.top_k == 50
    assert updated.top_p == pytest.approx(0.9)


def test_update_prompt_max_new_tokens(db):
    version = _make_version(db, name="upd-model-5")
    prompt = _make_prompt(db, version.id)
    updated = PromptService.update_prompt(db, prompt.id, max_new_tokens=256)
    assert updated.max_new_tokens == 256


def test_update_prompt_not_found_returns_none(db):
    assert PromptService.update_prompt(db, 9999, input_text="x") is None


def test_update_prompt_clears_stale_metrics(db):
    version = _make_version(db, name="upd-model-6")
    prompt = _make_prompt(db, version.id)

    metric = PromptMetric(
        prompt_id=prompt.id,
        entropy=2.0,
        is_anomaly=False,
        anomaly_reasons=[],
    )
    db.add(metric)
    db.commit()

    PromptService.update_prompt(db, prompt.id, input_text="Different input")

    count = db.query(PromptMetric).filter(PromptMetric.prompt_id == prompt.id).count()
    assert count == 0


def test_delete_prompt_success(db):
    version = _make_version(db, name="del-model-1")
    prompt = _make_prompt(db, version.id)
    assert PromptService.delete_prompt(db, prompt.id) is True
    assert PromptService.get_prompt_by_id(db, prompt.id) is None


def test_delete_prompt_missing_returns_false(db):
    assert PromptService.delete_prompt(db, 9999) is False


def test_get_prompts_filtered_by_version(db):
    v1 = _make_version(db, name="gp-model-1")

    model2 = Model(name="gp-model-2", source="hf:test/two", status=ModelStatus.ACTIVE)
    db.add(model2)
    db.flush()
    v2 = ModelVersion(model_id=model2.id, version="v1")
    db.add(v2)
    db.commit()
    db.refresh(v2)

    _make_prompt(db, v1.id, "p1")
    _make_prompt(db, v1.id, "p2")
    _make_prompt(db, v2.id, "p3")

    results = PromptService.get_prompts(db, model_version_id=v1.id)
    assert len(results) == 2
    assert all(p.model_version_id == v1.id for p in results)


def test_get_prompts_respects_limit(db):
    version = _make_version(db, name="gp-limit-model")
    for i in range(5):
        _make_prompt(db, version.id, f"prompt {i}")
    results = PromptService.get_prompts(db, limit=3)
    assert len(results) == 3


def test_get_prompts_respects_skip(db):
    version = _make_version(db, name="gp-skip-model")
    for i in range(5):
        _make_prompt(db, version.id, f"skip-prompt {i}")
    all_prompts = PromptService.get_prompts(db, model_version_id=version.id, limit=10)
    skipped = PromptService.get_prompts(db, model_version_id=version.id, skip=2, limit=10)
    assert len(skipped) == len(all_prompts) - 2


def test_calculate_metrics_returns_metric_object(db):
    version = _make_version(db, name="cm-model-1")
    prompt = _make_prompt(db, version.id)

    prompt.tokens = ["tok_10", "tok_11", "tok_12"]
    prompt.token_probabilities = {
        "0": {"tok_10": 0.7, "tok_11": 0.2, "tok_12": 0.1},
        "1": {"tok_10": 0.3, "tok_11": 0.6, "tok_12": 0.1},
    }
    prompt.output_length = 3
    db.commit()

    metric = PromptService.calculate_and_store_metrics(db, prompt.id)
    assert metric is not None
    assert metric.prompt_id == prompt.id
    assert metric.entropy is not None


def test_calculate_metrics_idempotent(db):
    version = _make_version(db, name="cm-model-2")
    prompt = _make_prompt(db, version.id)

    prompt.tokens = ["tok_a", "tok_b", "tok_c"]
    prompt.token_probabilities = {
        "0": {"tok_a": 0.8, "tok_b": 0.1, "tok_c": 0.1},
    }
    prompt.output_length = 3
    db.commit()

    PromptService.calculate_and_store_metrics(db, prompt.id)
    PromptService.calculate_and_store_metrics(db, prompt.id)

    count = db.query(PromptMetric).filter(PromptMetric.prompt_id == prompt.id).count()
    assert count == 1


def test_calculate_metrics_no_tokens_returns_none(db):
    version = _make_version(db, name="cm-model-3")
    prompt = _make_prompt(db, version.id)
    result = PromptService.calculate_and_store_metrics(db, prompt.id)
    assert result is None


def test_calculate_metrics_nonexistent_prompt_returns_none(db):
    result = PromptService.calculate_and_store_metrics(db, 9999)
    assert result is None


def test_get_prompt_metrics_found(db):
    version = _make_version(db, name="gpm-model-1")
    prompt = _make_prompt(db, version.id)

    metric = PromptMetric(
        prompt_id=prompt.id,
        entropy=1.5,
        is_anomaly=False,
        anomaly_reasons=[],
    )
    db.add(metric)
    db.commit()

    result = PromptService.get_prompt_metrics(db, prompt.id)
    assert result is not None
    assert result.prompt_id == prompt.id


def test_get_prompt_metrics_not_found_returns_none(db):
    assert PromptService.get_prompt_metrics(db, 9999) is None
