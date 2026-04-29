import numpy as np
from scipy.stats import entropy as scipy_entropy, wasserstein_distance
from scipy.spatial.distance import jensenshannon, cosine
from typing import List, Dict, Optional, Tuple
from collections import Counter
import math


class MetricsCalculator:
    """Calculator for statistical metrics on model outputs."""
    
    @staticmethod
    def calculate_entropy(token_probabilities: List[float]) -> float:
        """
        Calculate Shannon entropy of token probability distribution.
        
        Args:
            token_probabilities: List of probabilities for each token
            
        Returns:
            Entropy value
        """
        if not token_probabilities:
            return 0.0
        
        probs = [p for p in token_probabilities if p > 0]
        if not probs:
            return 0.0
        
        return float(scipy_entropy(probs, base=2))
    
    @staticmethod
    def calculate_kl_divergence(
        current_probs: List[float],
        reference_probs: List[float]
    ) -> float:
        """
        Calculate KL divergence between current and reference probability distributions.
        
        Args:
            current_probs: Current probability distribution
            reference_probs: Reference probability distribution
            
        Returns:
            KL divergence value
        """
        if not current_probs or not reference_probs:
            return 0.0
        
        if len(current_probs) != len(reference_probs):
            epsilon = 1e-10
            max_len = max(len(current_probs), len(reference_probs))
            current_probs = list(current_probs) + [epsilon] * (max_len - len(current_probs))
            reference_probs = list(reference_probs) + [epsilon] * (max_len - len(reference_probs))
        
        epsilon = 1e-10
        current_probs = [p + epsilon for p in current_probs]
        reference_probs = [p + epsilon for p in reference_probs]
        
        current_sum = sum(current_probs)
        reference_sum = sum(reference_probs)
        current_probs = [p / current_sum for p in current_probs]
        reference_probs = [p / reference_sum for p in reference_probs]
        
        kl_div = sum(
            p * math.log(p / q)
            for p, q in zip(current_probs, reference_probs)
        )
        
        return float(kl_div)

    @staticmethod
    def calculate_js_divergence(
        current_probs: List[float],
        reference_probs: List[float]
    ) -> float:
        """
        Calculate Jensen–Shannon divergence between two distributions.
        """
        if not current_probs or not reference_probs:
            return 0.0

        epsilon = 1e-10
        max_len = max(len(current_probs), len(reference_probs))
        current_probs = list(current_probs) + [epsilon] * (max_len - len(current_probs))
        reference_probs = list(reference_probs) + [epsilon] * (max_len - len(reference_probs))

        current_probs = np.array(current_probs, dtype=float)
        reference_probs = np.array(reference_probs, dtype=float)

        current_probs = current_probs / current_probs.sum()
        reference_probs = reference_probs / reference_probs.sum()

        return float(jensenshannon(current_probs, reference_probs, base=2.0))

    @staticmethod
    def calculate_wasserstein_distance(
        current_probs: List[float],
        reference_probs: List[float]
    ) -> float:
        """
        Calculate Wasserstein distance between two distributions.
        """
        if not current_probs or not reference_probs:
            return 0.0

        epsilon = 1e-10
        max_len = max(len(current_probs), len(reference_probs))
        current_probs = list(current_probs) + [epsilon] * (max_len - len(current_probs))
        reference_probs = list(reference_probs) + [epsilon] * (max_len - len(reference_probs))

        current_probs = np.array(current_probs, dtype=float)
        reference_probs = np.array(reference_probs, dtype=float)

        current_probs = current_probs / current_probs.sum()
        reference_probs = reference_probs / reference_probs.sum()

        positions = np.arange(len(current_probs))
        return float(wasserstein_distance(positions, positions, current_probs, reference_probs))
    
    @staticmethod
    def calculate_token_frequency(tokens: List[str]) -> Dict[str, float]:
        """
        Calculate token frequency distribution.
        
        Args:
            tokens: List of tokens
            
        Returns:
            Dictionary mapping token to frequency
        """
        if not tokens:
            return {}
        
        counter = Counter(tokens)
        total = len(tokens)
        
        return {token: count / total for token, count in counter.items()}

    @staticmethod
    def calculate_token_distribution_by_position(
        tokens: List[str],
        reference_tokens: Optional[List[str]] = None,
        rare_percentile: float = 0.1
    ) -> List[Dict[str, object]]:
        """
        Build per-position token stats for a single generation.

        Returns list of {position, token, is_new, is_rare}.
        """
        if not tokens:
            return []

        reference_tokens = reference_tokens or []
        reference_set = set(reference_tokens)
        ref_counter = Counter(reference_tokens) if reference_tokens else Counter()
        threshold = None
        if ref_counter:
            threshold = np.percentile(list(ref_counter.values()), rare_percentile * 100)

        result = []
        for idx, token in enumerate(tokens):
            is_new = token not in reference_set if reference_tokens else False
            is_rare = False
            if threshold is not None:
                is_rare = ref_counter.get(token, 0) <= threshold

            result.append({
                "position": idx,
                "token": token,
                "is_new": is_new,
                "is_rare": is_rare
            })

        return result

    @staticmethod
    def calculate_ngram_drift(
        tokens: List[str],
        reference_tokens: List[str],
        n: int = 2
    ) -> float:
        """
        Calculate n-gram distribution drift using Jensen–Shannon divergence.
        """
        if not tokens or not reference_tokens:
            return 0.0

        def ngrams(seq: List[str], n: int) -> List[str]:
            return [" ".join(seq[i:i + n]) for i in range(len(seq) - n + 1)]

        current_ngrams = ngrams(tokens, n)
        reference_ngrams = ngrams(reference_tokens, n)

        if not current_ngrams or not reference_ngrams:
            return 0.0

        current_freq = Counter(current_ngrams)
        reference_freq = Counter(reference_ngrams)

        all_keys = list(set(current_freq.keys()) | set(reference_freq.keys()))
        current_probs = np.array([current_freq.get(k, 0) for k in all_keys], dtype=float)
        reference_probs = np.array([reference_freq.get(k, 0) for k in all_keys], dtype=float)

        if current_probs.sum() == 0 or reference_probs.sum() == 0:
            return 0.0

        current_probs = current_probs / current_probs.sum()
        reference_probs = reference_probs / reference_probs.sum()

        return float(jensenshannon(current_probs, reference_probs, base=2.0))

    @staticmethod
    def calculate_embedding_drift(
        embeddings: List[List[float]],
        reference_embeddings: List[List[float]]
    ) -> float:
        """
        Calculate embedding distribution drift via cosine distance between mean embeddings.
        """
        if not embeddings or not reference_embeddings:
            return 0.0

        current_mean = np.mean(np.array(embeddings, dtype=float), axis=0)
        reference_mean = np.mean(np.array(reference_embeddings, dtype=float), axis=0)

        return float(cosine(current_mean, reference_mean))
    
    @staticmethod
    def calculate_rare_token_percentage(
        tokens: List[str],
        reference_tokens: List[str],
        percentile: float = 0.1
    ) -> float:
        """
        Calculate percentage of rare tokens compared to reference.
        
        Args:
            tokens: Current tokens
            reference_tokens: Reference token list
            percentile: Percentile threshold for rare tokens
            
        Returns:
            Percentage of rare tokens
        """
        if not tokens or not reference_tokens:
            return 0.0
        
        ref_counter = Counter(reference_tokens)
        threshold = np.percentile(list(ref_counter.values()), percentile * 100)
        
        rare_count = sum(1 for token in tokens if ref_counter.get(token, 0) <= threshold)
        
        return (rare_count / len(tokens)) * 100
    
    @staticmethod
    def calculate_new_token_percentage(
        tokens: List[str],
        reference_tokens: List[str]
    ) -> float:
        """
        Calculate percentage of tokens not seen in reference.
        
        Args:
            tokens: Current tokens
            reference_tokens: Reference token list
            
        Returns:
            Percentage of new tokens
        """
        if not tokens:
            return 0.0
        
        reference_set = set(reference_tokens)
        new_count = sum(1 for token in tokens if token not in reference_set)
        
        return (new_count / len(tokens)) * 100
    
    @staticmethod
    def calculate_length_statistics(lengths: List[int]) -> Tuple[float, float, float]:
        """
        Calculate length statistics.
        
        Args:
            lengths: List of output lengths
            
        Returns:
            Tuple of (mean, median, variance)
        """
        if not lengths:
            return 0.0, 0.0, 0.0
        
        mean = float(np.mean(lengths))
        median = float(np.median(lengths))
        variance = float(np.var(lengths))
        
        return mean, median, variance
    
    @staticmethod
    def detect_anomaly(
        metric_value: float,
        threshold: float,
        comparison_operator: str
    ) -> bool:
        """
        Detect if metric value is anomalous based on threshold.
        
        Args:
            metric_value: Value to check
            threshold: Threshold value
            comparison_operator: Comparison operator (>, <, >=, <=, ==)
            
        Returns:
            True if anomaly detected, False otherwise
        """
        operators = {
            '>': lambda x, y: x > y,
            '<': lambda x, y: x < y,
            '>=': lambda x, y: x >= y,
            '<=': lambda x, y: x <= y,
            '==': lambda x, y: abs(x - y) < 1e-6
        }
        
        op_func = operators.get(comparison_operator)
        if not op_func:
            return False
        
        return op_func(metric_value, threshold)
    
    @staticmethod
    def calculate_aggregated_metrics(
        entropies: List[float],
        kl_divergences: List[float],
        generation_times: List[float],
        output_lengths: List[int],
        anomaly_flags: List[bool]
    ) -> Dict[str, float]:
        """
        Calculate aggregated metrics from multiple prompts.
        
        Args:
            entropies: List of entropy values
            kl_divergences: List of KL divergence values
            generation_times: List of generation times
            output_lengths: List of output lengths
            anomaly_flags: List of anomaly flags
            
        Returns:
            Dictionary of aggregated metrics
        """
        total_prompts = len(entropies)
        
        if total_prompts == 0:
            return {
                'total_prompts': 0,
                'avg_entropy': 0.0,
                'avg_kl_divergence': 0.0,
                'avg_generation_time': 0.0,
                'avg_output_length': 0.0,
                'anomaly_count': 0,
                'anomaly_percentage': 0.0
            }
        
        anomaly_count = sum(anomaly_flags)
        
        return {
            'total_prompts': total_prompts,
            'avg_entropy': float(np.mean(entropies)) if entropies else 0.0,
            'avg_kl_divergence': float(np.mean(kl_divergences)) if kl_divergences else 0.0,
            'avg_generation_time': float(np.mean(generation_times)) if generation_times else 0.0,
            'avg_output_length': float(np.mean(output_lengths)) if output_lengths else 0.0,
            'anomaly_count': anomaly_count,
            'anomaly_percentage': (anomaly_count / total_prompts) * 100
        }
