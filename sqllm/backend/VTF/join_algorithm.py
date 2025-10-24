from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class JoinCriterion:
    """Single join criterion (column + mechanism + weight)."""

    column: str
    mechanism: str
    weight: float


@dataclass
class JoinAlgorithm:
    """Parsed join algorithm specification."""

    k_value: int
    criteria: list[JoinCriterion]


def parse_algorithm(algorithm_str: str) -> JoinAlgorithm:
    """
    Parse algorithm string like:
    '5: name semantic_distance, price numeric_distance 1.5, category exact_match'
    """
    parts = algorithm_str.split(":", 1)
    k_value = int(parts[0].strip())
    criteria_str = parts[1].strip()

    criteria = []
    for idx, criterion_str in enumerate(criteria_str.split(",")):
        tokens = criterion_str.strip().split()
        column = tokens[0]
        mechanism = tokens[1]
        weight = float(tokens[2]) if len(tokens) > 2 else _default_weight(idx)
        criteria.append(JoinCriterion(column, mechanism, weight))

    return JoinAlgorithm(k_value, criteria)


def _default_weight(index: int) -> float:
    """Inverse Fibonacci weights: 1.0, 0.618, 0.382, 0.236, ..."""
    phi = 1.618033988749895
    if index == 0:
        return 1.0
    return 1.0 / (phi**index)


class SimilarityScorer:
    """Computes and caches similarity scores for join criteria."""

    def __init__(
        self,
        left_df: pd.DataFrame,
        right_df: pd.DataFrame,
        criteria: list[JoinCriterion],
    ):
        self.left_df = left_df
        self.right_df = right_df
        self.criteria = criteria
        self._cache = {}
        self._precompute_all()

    def _precompute_all(self):
        """Pre-compute similarity matrices for all criteria."""
        for criterion in self.criteria:
            col = criterion.column
            mechanism = criterion.mechanism

            if mechanism == "semantic_distance":
                self._cache[col] = self._compute_semantic_similarities(col)
            elif mechanism == "fuzzy_match":
                self._cache[col] = self._compute_fuzzy_similarities(col)
            elif mechanism == "exact_match":
                self._cache[col] = self._compute_exact_matches(col)
            elif mechanism in ("arithmetic_asc", "arithmetic_desc"):
                self._cache[col] = self._compute_numeric_similarities(col, mechanism)
            elif mechanism == "numeric_distance":
                self._cache[col] = self._compute_numeric_distance(col)

    def get_top_candidates(
        self, left_row_idx: int, k: int
    ) -> list[tuple[int, float, dict]]:
        """
        Get top k right table rows for a left row.
        Returns: [(right_idx, combined_score, score_breakdown), ...]
        """
        n_right = len(self.right_df)
        scores = np.ones(n_right)
        breakdown = {criterion.column: np.zeros(n_right) for criterion in self.criteria}

        for criterion in self.criteria:
            col = criterion.column
            col_scores = self._cache[col][left_row_idx]
            breakdown[col] = col_scores
            scores *= np.power(col_scores, criterion.weight)

        # Get top k indices
        top_k = min(k, n_right)
        top_indices = np.argsort(scores)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            score_dict = {col: breakdown[col][idx] for col in breakdown}
            results.append((int(idx), float(scores[idx]), score_dict))

        return results

    def _compute_semantic_similarities(self, col: str) -> np.ndarray:
        """Compute semantic similarity matrix using embeddings."""
        from sklearn.metrics.pairwise import cosine_similarity
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        left_texts = self.left_df[col].fillna("").astype(str).tolist()
        right_texts = self.right_df[col].fillna("").astype(str).tolist()

        left_embeddings = model.encode(left_texts)
        right_embeddings = model.encode(right_texts)

        return cosine_similarity(left_embeddings, right_embeddings)

    def _compute_fuzzy_similarities(self, col: str) -> np.ndarray:
        """Compute fuzzy string similarity matrix."""
        from rapidfuzz import fuzz

        left_vals = self.left_df[col].fillna("").astype(str).tolist()
        right_vals = self.right_df[col].fillna("").astype(str).tolist()

        matrix = np.zeros((len(left_vals), len(right_vals)))
        for i, left_val in enumerate(left_vals):
            for j, right_val in enumerate(right_vals):
                matrix[i, j] = fuzz.ratio(left_val, right_val) / 100.0

        return matrix

    def _compute_exact_matches(self, col: str) -> np.ndarray:
        """Compute exact match matrix (1.0 or 0.0)."""
        left_vals = self.left_df[col].values[:, None]
        right_vals = self.right_df[col].values[None, :]
        return (left_vals == right_vals).astype(float)

    def _compute_numeric_similarities(self, col: str, mechanism: str) -> np.ndarray:
        """Compute similarity based on numeric ordering."""
        left_vals = pd.to_numeric(self.left_df[col], errors="coerce").fillna(0).values
        right_vals = pd.to_numeric(self.right_df[col], errors="coerce").fillna(0).values

        if mechanism == "arithmetic_asc":
            right_sorted_idx = np.argsort(right_vals)
        else:  # arithmetic_desc
            right_sorted_idx = np.argsort(right_vals)[::-1]

        # Create score matrix based on rank proximity
        n_left, n_right = len(left_vals), len(right_vals)
        matrix = np.zeros((n_left, n_right))

        for i, left_val in enumerate(left_vals):
            left_rank = np.searchsorted(np.sort(right_vals), left_val)
            for j in range(n_right):
                right_rank = np.where(right_sorted_idx == j)[0][0]
                rank_diff = abs(left_rank - right_rank)
                matrix[i, j] = 1.0 / (1.0 + rank_diff / n_right)

        return matrix

    def _compute_numeric_distance(self, col: str) -> np.ndarray:
        """Compute normalized numeric distance."""
        left_vals = pd.to_numeric(self.left_df[col], errors="coerce").fillna(0).values
        right_vals = pd.to_numeric(self.right_df[col], errors="coerce").fillna(0).values

        distances = np.abs(left_vals[:, None] - right_vals[None, :])
        max_dist = distances.max()

        if max_dist > 0:
            return 1.0 - (distances / max_dist)
        return np.ones_like(distances)
