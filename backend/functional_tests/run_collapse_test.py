from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "functional-test-secret-key-do-not-use")
os.environ.setdefault("ENFORCE_HTTPS", "False")
os.environ.setdefault("ENCRYPT_DATA", "False")
os.environ.setdefault("DEBUG", "False")

THIS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = (THIS_DIR.parent).resolve()
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import numpy as np
import pandas as pd

from app.services.wikitext_service import (
    CUSTOM_DATASET_DIR,
    calculate_wikitext_benchmark_metrics,
    store_custom_dataset,
)


COLLAPSE_DIR = (BACKEND_DIR.parent / "notebooks" / "collapse_models").resolve()
MODELS_ROOT = COLLAPSE_DIR / "models"
GROUND_TRUTH_CSV = COLLAPSE_DIR / "collapse_metrics.csv"
RESULTS_DIR = THIS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _ensure_test_dataset(n_rows: int = 500, *, force: bool = False,
                         max_chars: int = 1000) -> str:
    """Materialise a real TinyStories slice as a custom dataset.

    Index range 30000+ keeps it disjoint from the notebook's train+heldout
    subset. The max_chars filter keeps prompt + max_new_tokens under
    distilgpt2's 1024-position context.
    """
    dataset_filename = "tinystories_functional_test.jsonl"
    target = CUSTOM_DATASET_DIR / dataset_filename
    if target.exists() and target.stat().st_size > 0 and not force:
        first_line = target.read_text(encoding="utf-8").splitlines()[0]
        try:
            first_text = json.loads(first_line)["text"]
        except Exception:
            first_text = ""
        with target.open(encoding="utf-8") as fh:
            n_existing = sum(1 for _ in fh)
        if n_existing >= n_rows and len(first_text) <= max_chars * 2:
            print(f"  reusing existing custom dataset → {target} ({n_existing} rows)")
            return f"custom:{dataset_filename}"
        print(f"  cached dataset unsuitable (rows={n_existing}, sample_len={len(first_text)}) — regenerating")

    print(f"  downloading TinyStories slice (target {n_rows} rows, max_chars={max_chars})...")
    from datasets import load_dataset
    ds = load_dataset("roneneldan/TinyStories", split="train")
    start = 30_000
    rows: List[str] = []
    i = 0
    while len(rows) < n_rows and start + i < len(ds):
        text = ds[start + i]["text"]
        if 50 < len(text) <= max_chars:
            rows.append(text)
        i += 1
    if len(rows) < n_rows:
        print(f"  warning: only collected {len(rows)} short rows after scanning {i}")
    payload = "\n".join(json.dumps({"text": t}, ensure_ascii=False) for t in rows)
    info = store_custom_dataset(dataset_filename, payload.encode("utf-8"))
    print(f"  uploaded  {info['id']}  ({target.stat().st_size / 1024:.1f} KB, {len(rows)} rows)")
    return info["id"]


def _benchmark_checkpoint(
    *,
    gen_idx: int,
    checkpoint_path: Path,
    dataset_id: str,
    sample_count: int,
    max_new_tokens: int,
    seed: int,
) -> Dict[str, Any]:
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")

    print(f"\n gen_{gen_idx}  ({checkpoint_path.name}) ━━")
    t0 = time.perf_counter()
    res = calculate_wikitext_benchmark_metrics(
        model_id=None,
        local_path=str(checkpoint_path),
        dataset_id=dataset_id,
        sample_count=sample_count,
        max_new_tokens=max_new_tokens,
        max_tokens=4000,
        temperature=0.7,
        num_beams=1,
        top_k=20,
        rare_percentile=0.1,
        seed=seed,
    )
    res["generation"] = gen_idx
    res["wall_clock_s"] = round(time.perf_counter() - t0, 2)

    print(
        f"  entropy={res['entropy']:.3f}  "
        f"perplexity={res['perplexity']:.2f}  "
        f"avg_seq_ppl={res.get('avg_sequence_perplexity', 0):.2f}  "
        f"vocab={res['vocab_size']}  "
        f"js_div={res['js_divergence']:.4f}  "
        f"rare_token%={res['rare_token_percentage']:.2f}  "
        f"({res['wall_clock_s']}s)"
    )
    return res


def _check_assertions(report: pd.DataFrame, *, max_gen: int) -> List[str]:
    failures: List[str] = []
    df = report.set_index("generation").sort_index()

    def _monotone(label: str, series: pd.Series, direction: str,
                  tol_violations: int = 1) -> None:
        s = series.dropna()
        diffs = s.diff().dropna()
        if direction == "up":
            n_ok = int((diffs > 0).sum())
        elif direction == "down":
            n_ok = int((diffs < 0).sum())
        else:
            raise ValueError(direction)
        n_total = len(diffs)
        if n_total == 0:
            return
        if n_ok < n_total - tol_violations:
            failures.append(
                f"{label}: only {n_ok}/{n_total} successive generations moved "
                f"{'upward' if direction == 'up' else 'downward'} "
                f"(tolerance: {tol_violations} violation(s))"
            )


    n_steps = max(1, len(df) - 1)
    tol = max(2, n_steps * 2 // 5)

    _monotone("entropy of generated text",     df["app_entropy"],         "down", tol_violations=tol)
    _monotone("perplexity ",                   df["app_perplexity"],      "down", tol_violations=tol)
    _monotone("vocab size of generated text",  df["app_vocab_size"],      "down", tol_violations=tol)
    _monotone("rare-token percentage",         df["app_rare_token_pct"],  "down", tol_violations=tol)

    _monotone("JS divergence vs real reference", df["app_js_divergence"], "up", tol_violations=tol)

    if df["app_avg_seq_perplexity"].notna().any():
        _monotone("avg_sequence_perplexity",   df["app_avg_seq_perplexity"], "down",
                  tol_violations=tol)

    if 0 in df.index and max_gen in df.index:
        if df.loc[max_gen, "app_entropy"] >= df.loc[0, "app_entropy"]:
            failures.append(
                f"M_{max_gen} generation entropy ({df.loc[max_gen, 'app_entropy']:.3f}) "
                f"did not fall below M_0 ({df.loc[0, 'app_entropy']:.3f}) — collapse not detected"
            )
        if df.loc[max_gen, "app_vocab_size"] >= df.loc[0, "app_vocab_size"]:
            failures.append(
                f"M_{max_gen} vocab ({int(df.loc[max_gen, 'app_vocab_size'])}) did not "
                f"shrink relative to M_0 ({int(df.loc[0, 'app_vocab_size'])})"
            )
        if df.loc[max_gen, "app_js_divergence"] <= df.loc[0, "app_js_divergence"]:
            failures.append(
                f"M_{max_gen} JS-div ({df.loc[max_gen, 'app_js_divergence']:.4f}) is not "
                f"greater than M_0 ({df.loc[0, 'app_js_divergence']:.4f})"
            )

    return failures


def _save_plot(report: pd.DataFrame, out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  matplotlib not available — skipping plot")
        return

    df = report.sort_values("generation")
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))

    axes[0, 0].plot(df["generation"], df["gt_perplexity"], "s-", color="#c0392b", lw=2)
    axes[0, 0].set_title("Notebook ground truth\nperplexity on real heldout (↑ = collapse)")
    axes[0, 0].set_xlabel("generation"); axes[0, 0].set_ylabel("perplexity")
    axes[0, 0].grid(alpha=0.3)

    axes[0, 1].plot(df["generation"], df["app_perplexity"], "o-", color="#2980b9", lw=2)
    axes[0, 1].set_title("App benchmark\nperplexity = $2^{H(\\mathrm{generated})}$  (↓ = collapse)")
    axes[0, 1].set_xlabel("generation"); axes[0, 1].set_ylabel("perplexity")
    axes[0, 1].grid(alpha=0.3)

    axes[0, 2].plot(df["generation"], df["app_avg_seq_perplexity"], "o-", color="#16a085", lw=2)
    axes[0, 2].set_title("App benchmark\navg sequence perplexity on own outputs (↓ = collapse)")
    axes[0, 2].set_xlabel("generation"); axes[0, 2].set_ylabel("perplexity")
    axes[0, 2].grid(alpha=0.3)

    axes[1, 0].plot(df["generation"], df["app_vocab_size"], "o-", color="#2c3e50", lw=2)
    axes[1, 0].set_title("App benchmark\nvocab size in generations (↓ = collapse)")
    axes[1, 0].set_xlabel("generation"); axes[1, 0].set_ylabel("unique tokens")
    axes[1, 0].grid(alpha=0.3)

    axes[1, 1].plot(df["generation"], df["app_entropy"], "o-", color="#27ae60", lw=2)
    axes[1, 1].set_title("App benchmark\ntoken entropy of generations (↓ = collapse)")
    axes[1, 1].set_xlabel("generation"); axes[1, 1].set_ylabel("entropy (bits)")
    axes[1, 1].grid(alpha=0.3)

    axes[1, 2].plot(df["generation"], df["app_js_divergence"], "o-", color="#d35400", lw=2)
    axes[1, 2].set_title("App benchmark\nJS divergence vs real reference (↑ = drift)")
    axes[1, 2].set_xlabel("generation"); axes[1, 2].set_ylabel("JS divergence")
    axes[1, 2].grid(alpha=0.3)

    fig.suptitle("LLM Collapse Detector — functional verification on distilgpt2 + TinyStories",
                 fontsize=13, y=1.00)
    plt.tight_layout()
    plt.savefig(out_path, dpi=130, bbox_inches="tight")
    print(f"  saved plot → {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Functional test for collapse detection")
    parser.add_argument("--sample-count", type=int, default=20,
                        help="prompts to sample per checkpoint (default 20; use larger on GPU)")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--n-test-rows", type=int, default=500,
                        help="number of held-out TinyStories rows to use as benchmark dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generations", type=int, nargs="+", default=list(range(6)),
                        help="which gen indexes to evaluate")
    parser.add_argument("--rebuild-dataset", action="store_true",
                        help="force regeneration of the cached test dataset")
    args = parser.parse_args()

    if not GROUND_TRUTH_CSV.exists():
        print(f"ERROR: ground-truth metrics not found at {GROUND_TRUTH_CSV}", file=sys.stderr)
        return 2

    print(f"  models   : {MODELS_ROOT}")
    print(f"  ground   : {GROUND_TRUTH_CSV}")
    print(f"  results  : {RESULTS_DIR}")
    print(f"  config   : sample_count={args.sample_count}  "
          f"max_new_tokens={args.max_new_tokens}  seed={args.seed}")

    print("\n[1/4] preparing real held-out test corpus")
    dataset_id = _ensure_test_dataset(args.n_test_rows, force=args.rebuild_dataset)

    print(f"\n[2/4] benchmarking {len(args.generations)} checkpoint(s)")
    raw_results: List[Dict[str, Any]] = []
    for gen_idx in args.generations:
        ckpt = MODELS_ROOT / f"gen_{gen_idx}"
        try:
            res = _benchmark_checkpoint(
                gen_idx=gen_idx,
                checkpoint_path=ckpt,
                dataset_id=dataset_id,
                sample_count=args.sample_count,
                max_new_tokens=args.max_new_tokens,
                seed=args.seed,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED on gen_{gen_idx}: {exc.__class__.__name__}: {exc}",
                  file=sys.stderr)
            return 3
        raw_results.append(res)

    print("\n[3/4] building report")
    rows = []
    for r in raw_results:
        rows.append({
            "generation": r["generation"],
            "app_entropy": r["entropy"],
            "app_perplexity": r["perplexity"],
            "app_avg_seq_perplexity": r.get("avg_sequence_perplexity"),
            "app_reference_entropy": r.get("reference_entropy"),
            "app_reference_perplexity": r.get("reference_perplexity"),
            "app_js_divergence": r["js_divergence"],
            "app_vocab_size": r["vocab_size"],
            "app_token_count": r["token_count"],
            "app_rare_token_pct": r["rare_token_percentage"],
            "wall_clock_s": r["wall_clock_s"],
        })
    df_app = pd.DataFrame(rows)

    df_gt = pd.read_csv(GROUND_TRUTH_CSV)[
        ["generation", "perplexity_real_heldout", "corpus_vocab_size", "corpus_entropy"]
    ].rename(columns={
        "perplexity_real_heldout": "gt_perplexity",
        "corpus_vocab_size":       "gt_corpus_vocab",
        "corpus_entropy":          "gt_corpus_entropy",
    })
    report = df_app.merge(df_gt, on="generation", how="left").sort_values("generation")

    csv_path = RESULTS_DIR / "functional_collapse_results.csv"
    report.to_csv(csv_path, index=False)
    print(f"  saved CSV → {csv_path}")

    pd.set_option("display.float_format", lambda v: f"{v:.4f}" if isinstance(v, float) else str(v))
    print("\ntrajectory")
    print(report.to_string(index=False))

    plot_path = RESULTS_DIR / "functional_collapse.png"
    _save_plot(report, plot_path)

    correlations: Dict[str, float] = {}
    if report["gt_perplexity"].notna().all() and len(report) >= 3:
        for col in ("app_entropy", "app_perplexity", "app_vocab_size",
                    "app_rare_token_pct", "app_js_divergence", "app_avg_seq_perplexity"):
            if col in report.columns and report[col].notna().all():
                correlations[col] = float(np.corrcoef(report[col], report["gt_perplexity"])[0, 1])
        print("\nPearson  vs ground-truth perplexity")
        for k, v in correlations.items():
            print(f"  ({k:<25s}, gt_perplexity) = {v:+.4f}")

    print("\n[4/4] assertions")
    max_gen = int(report["generation"].max())
    failures = _check_assertions(report, max_gen=max_gen)

    rho_threshold = 0.6 if args.sample_count < 100 else 0.85
    primary_neg_ok = any(
        v <= -rho_threshold
        for k, v in correlations.items()
        if k in {"app_vocab_size", "app_rare_token_pct"}
    )
    primary_pos_ok = correlations.get("app_js_divergence", 0.0) >= rho_threshold
    if not (primary_neg_ok and primary_pos_ok):
        failures.append(
            f"primary collapse signals weak — "
            f"need vocab_size or rare_token_pct ρ ≤ −{rho_threshold:.2f} AND "
            f"js_divergence ρ ≥ +{rho_threshold:.2f}"
        )

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nAll collapse assertions passed.")
    if max_gen in report["generation"].values and 0 in report["generation"].values:
        first = report[report["generation"] == 0].iloc[0]
        last = report[report["generation"] == max_gen].iloc[0]

        def _delta(metric: str, fmt: str = ".3f") -> str:
            d = last[metric] - first[metric]
            sign = "+" if d >= 0 else ""
            return f"{first[metric]:{fmt}} → {last[metric]:{fmt}}  ({sign}{d:{fmt}})"

        print(f"  entropy           gen_0 → gen_{max_gen}: {_delta('app_entropy')}")
        print(f"  perplexity        gen_0 → gen_{max_gen}: {_delta('app_perplexity')}")
        print(f"  vocab_size        gen_0 → gen_{max_gen}: "
              f"{int(first['app_vocab_size'])} → {int(last['app_vocab_size'])}  "
              f"({int(last['app_vocab_size'] - first['app_vocab_size']):+d})")
        print(f"  js_divergence     gen_0 → gen_{max_gen}: {_delta('app_js_divergence', '.4f')}")
        print(f"  rare_token_pct    gen_0 → gen_{max_gen}: {_delta('app_rare_token_pct', '.2f')}")
        print(f"  avg_seq_perplexity gen_0 → gen_{max_gen}: {_delta('app_avg_seq_perplexity', '.3f')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
