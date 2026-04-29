import math

import pytest

from app.services.metrics_calculator import MetricsCalculator


def test_entropy_uniform_distribution_matches_log2_n():
    probs = [0.25] * 4
    entropy = MetricsCalculator.calculate_entropy(probs)
    assert math.isclose(entropy, 2.0, rel_tol=1e-6)


def test_entropy_degenerate_distribution_is_zero():
    assert MetricsCalculator.calculate_entropy([1.0, 0.0, 0.0]) == 0.0


def test_kl_divergence_zero_for_identical_distributions():
    p = [0.2, 0.3, 0.5]
    assert MetricsCalculator.calculate_kl_divergence(p, p) == pytest.approx(0.0, abs=1e-9)


def test_js_divergence_is_symmetric():
    p = [0.5, 0.5]
    q = [0.9, 0.1]
    forward = MetricsCalculator.calculate_js_divergence(p, q)
    reverse = MetricsCalculator.calculate_js_divergence(q, p)
    assert forward == pytest.approx(reverse, rel=1e-9)


def test_js_divergence_bounded_in_zero_to_one():
    p = [1.0, 0.0]
    q = [0.0, 1.0]
    js = MetricsCalculator.calculate_js_divergence(p, q)
    assert 0.0 <= js <= 1.0001


def test_token_frequency_counts_repeats():
    freq = MetricsCalculator.calculate_token_frequency(["a", "b", "a", "c", "a"])
    assert freq["a"] == 3
    assert freq["b"] == 1


def test_length_statistics_handles_empty():
    mean, median, variance = MetricsCalculator.calculate_length_statistics([])
    assert mean == 0 or mean is None or math.isclose(mean, 0.0)
