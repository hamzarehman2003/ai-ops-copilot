"""Cross-encoder reranker: reads (query, chunk) *together* and scores how well they match.

Retrieval (bi-encoder + keyword search) is fast because queries and chunks are encoded
separately; a cross-encoder is slower but much more precise, so it only re-orders the top
candidates. Default: ms-marco-MiniLM-L-6-v2 (ONNX via fastembed, ~80 MB, CPU).

Scores are unbounded logits (higher = more relevant); `min_rerank_score` in settings turns
them into an "is anything relevant at all?" decision for abstaining.
"""

import math
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class Reranker(Protocol):
    model_name: str

    def score(self, query: str, documents: list[str]) -> list[float]: ...


class FastEmbedReranker:
    def __init__(self, model_name: str, cache_dir: Path) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name
        self._model = TextCrossEncoder(model_name, cache_dir=str(cache_dir))

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        return [float(s) for s in self._model.rerank(query, documents, batch_size=32)]


@lru_cache
def get_reranker() -> Reranker:
    settings = get_settings()
    return FastEmbedReranker(settings.reranker_model, settings.model_cache_dir)


def relevance(score: float) -> float:
    """Squash a logit into 0..1 for display only (decisions use the raw score)."""
    return 1 / (1 + math.exp(-score))
