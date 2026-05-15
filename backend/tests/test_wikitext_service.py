from __future__ import annotations

import json

import pytest

from app.services.wikitext_service import (
    DEFAULT_DATASET_ID,
    list_available_datasets,
    store_custom_dataset,
)


def _make_wikitext_stub():
    import torch

    class StubTokenizer:
        eos_token_id = 0
        pad_token_id = 0

        def __call__(self, text, return_tensors=None, **kwargs):
            ids = torch.tensor([[1, 2, 3]])
            return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}

        def tokenize(self, text):
            return text.split()[:4]

        def convert_ids_to_tokens(self, ids):
            return [f"tok_{i}" for i in ids]

        def convert_tokens_to_string(self, tokens):
            return " ".join(str(t) for t in tokens)

        def decode(self, ids, skip_special_tokens=True):
            return "generated text"

    class StubModel:
        def eval(self):
            return self

        def generate(self, input_ids=None, **kwargs):
            max_new = int(kwargs.get("max_new_tokens", 4))
            new_toks = torch.arange(10, 10 + max_new).unsqueeze(0)
            return torch.cat([input_ids, new_toks], dim=1)

        def __call__(self, input_ids=None, labels=None, **kwargs):
            class _R:
                loss = torch.tensor(2.5)

            return _R()

    return StubTokenizer(), StubModel()


@pytest.fixture()
def wiki_patched(monkeypatch):
    tokenizer, model = _make_wikitext_stub()

    monkeypatch.setattr(
        "app.services.wikitext_service._load_model_and_tokenizer",
        lambda model_id, local_path=None: (tokenizer, model),
    )
    monkeypatch.setattr(
        "app.services.wikitext_service._load_dataset_rows",
        lambda dataset_id: (
            "Test Dataset",
            [
                "The quick brown fox jumps over the lazy dog.",
                "This is another test sentence for benchmarking purposes.",
                "Language models generate text by predicting the next token.",
                "Neural networks learn patterns from large amounts of data.",
            ],
        ),
    )
    return tokenizer, model


def test_benchmark_returns_expected_keys(wiki_patched):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    result = calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2, max_new_tokens=4)

    for key in (
        "entropy", "perplexity", "token_count", "vocab_size", "js_divergence",
        "rare_token_percentage", "top_tokens", "prompts_used", "dataset",
        "avg_sequence_perplexity", "std_sequence_perplexity",
        "reference_entropy", "reference_perplexity",
    ):
        assert key in result, f"Missing key: {key}"


def test_benchmark_entropy_is_non_negative(wiki_patched):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    result = calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2, max_new_tokens=4)
    assert result["entropy"] >= 0.0
    assert result["perplexity"] >= 0.0


def test_benchmark_with_seed_is_reproducible(wiki_patched):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    r1 = calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2, seed=99)
    r2 = calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2, seed=99)
    assert r1["entropy"] == pytest.approx(r2["entropy"])
    assert r1["token_count"] == r2["token_count"]


def test_benchmark_with_num_beams(wiki_patched):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    result = calculate_wikitext_benchmark_metrics(
        model_id="test/model",
        sample_count=2,
        max_new_tokens=4,
        num_beams=2,
        temperature=0.0,
    )
    assert result["prompts_used"] >= 1
    assert result["num_beams"] == 2


def test_benchmark_top_k_limits_top_tokens(wiki_patched):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    result = calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=3, top_k=5)
    assert len(result["top_tokens"]) <= 5


def test_benchmark_empty_dataset_raises(monkeypatch):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    monkeypatch.setattr(
        "app.services.wikitext_service._load_dataset_rows",
        lambda dataset_id: ("Empty", []),
    )
    monkeypatch.setattr(
        "app.services.wikitext_service._load_model_and_tokenizer",
        lambda *args, **kwargs: _make_wikitext_stub(),
    )

    with pytest.raises(ValueError, match="empty"):
        calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2)


def test_benchmark_no_usable_rows_raises(monkeypatch):
    from app.services.wikitext_service import calculate_wikitext_benchmark_metrics

    monkeypatch.setattr(
        "app.services.wikitext_service._load_dataset_rows",
        lambda dataset_id: ("Headings Only", ["= Heading =", "= Another ="]),
    )
    monkeypatch.setattr(
        "app.services.wikitext_service._load_model_and_tokenizer",
        lambda *args, **kwargs: _make_wikitext_stub(),
    )

    with pytest.raises(ValueError, match="no usable rows"):
        calculate_wikitext_benchmark_metrics(model_id="test/model", sample_count=2)


def test_store_custom_dataset_txt(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    content = b"line one\nline two\nline three\n"
    result = store_custom_dataset("mydata.txt", content)
    assert result["id"] == "custom:mydata.txt"
    assert result["label"] == "Custom: mydata.txt"
    assert (tmp_path / "mydata.txt").read_bytes() == content


def test_store_custom_dataset_json(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    content = json.dumps([{"text": "hello"}, {"text": "world"}]).encode()
    result = store_custom_dataset("test.json", content)
    assert result["id"] == "custom:test.json"


def test_store_custom_dataset_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    content = b'{"text": "first"}\n{"text": "second"}\n'
    result = store_custom_dataset("data.jsonl", content)
    assert result["id"] == "custom:data.jsonl"


def test_store_custom_dataset_invalid_extension_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        store_custom_dataset("bad.xyz", b"content")


def test_store_custom_dataset_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    store_custom_dataset("mydata.txt", b"first content")
    store_custom_dataset("mydata.txt", b"second content")
    assert (tmp_path / "mydata.txt").read_bytes() == b"second content"


def test_list_available_datasets_includes_default(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    datasets = list_available_datasets()
    ids = [d["id"] for d in datasets]
    assert DEFAULT_DATASET_ID in ids


def test_list_available_datasets_includes_custom_txt(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "corpus.txt").write_text("hello world")
    datasets = list_available_datasets()
    ids = [d["id"] for d in datasets]
    assert "custom:corpus.txt" in ids


def test_list_available_datasets_includes_multiple_formats(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "data.csv").write_text("col\nvalue")
    (tmp_path / "data.jsonl").write_text('{"text":"a"}\n')
    (tmp_path / "data.json").write_text('[{"text":"b"}]')
    datasets = list_available_datasets()
    ids = [d["id"] for d in datasets]
    assert "custom:data.csv" in ids
    assert "custom:data.jsonl" in ids
    assert "custom:data.json" in ids


def test_list_available_datasets_excludes_unsupported_extensions(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "ignore.xyz").write_text("bad")
    (tmp_path / "ignore.docx").write_text("bad")
    datasets = list_available_datasets()
    ids = [d["id"] for d in datasets]
    assert "custom:ignore.xyz" not in ids
    assert "custom:ignore.docx" not in ids


def test_list_available_datasets_excludes_subdirectories(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "subdir").mkdir()
    datasets = list_available_datasets()
    ids = [d["id"] for d in datasets]
    assert "custom:subdir" not in ids


def test_load_custom_txt_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "corpus.txt").write_text("line one\nline two\n")
    from app.services.wikitext_service import _load_dataset_rows

    label, rows = _load_dataset_rows("custom:corpus.txt")
    assert "corpus.txt" in label
    assert "line one" in rows


def test_load_custom_json_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "data.json").write_text(json.dumps([{"text": "hello"}, {"text": "world"}]))
    from app.services.wikitext_service import _load_dataset_rows

    _label, rows = _load_dataset_rows("custom:data.json")
    assert "hello" in rows
    assert "world" in rows


def test_load_custom_jsonl_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    (tmp_path / "data.jsonl").write_bytes(b'{"text": "first"}\n{"text": "second"}\n')
    from app.services.wikitext_service import _load_dataset_rows

    _label, rows = _load_dataset_rows("custom:data.jsonl")
    assert "first" in rows
    assert "second" in rows


def test_load_unknown_dataset_id_raises(monkeypatch):
    from app.services.wikitext_service import _load_dataset_rows

    with pytest.raises(ValueError, match="Unknown dataset_id"):
        _load_dataset_rows("unknown:something")


def test_load_missing_custom_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.wikitext_service.CUSTOM_DATASET_DIR", tmp_path)
    from app.services.wikitext_service import _load_dataset_rows

    with pytest.raises(ValueError, match="not found"):
        _load_dataset_rows("custom:nonexistent.txt")
