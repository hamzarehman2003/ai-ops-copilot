"""Text -> vector, behind a tiny adapter so the model can be swapped (and compared in evals).

Default: BAAI/bge-small-en-v1.5 via fastembed (ONNX, runs on CPU, no API key, 384 dims,
max 512 input tokens). Vectors come back L2-normalized, so cosine distance is the metric.

Two details that silently hurt quality when missed:
- Documents and queries are embedded differently. BGE recommends an instruction prefix on
  short *queries* only; documents are embedded as-is.
- Inputs longer than the model's limit are truncated without an error, so the chunker's token
  budget (counted with tiktoken) must leave room under 512 tokens of *this* model's tokenizer
  (tests/test_embeddings.py checks every demo chunk).
"""

from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.config import get_settings

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
MAX_INPUT_TOKENS = 512


class Embedder(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str, cache_dir: Path) -> None:
        from fastembed import TextEmbedding  # heavy import: only when actually embedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name, cache_dir=str(cache_dir))
        self._query_prefix = BGE_QUERY_INSTRUCTION if "bge" in model_name.lower() else ""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.embed([self._query_prefix + text]))).tolist()

    @property
    def tokenizer(self):
        return self._model.model.tokenizer


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return FastEmbedEmbedder(settings.embedding_model, settings.model_cache_dir)


def embedding_text(heading_path: list[str], content: str) -> str:
    """What gets embedded: the heading path as a "contextual chunk header", then the chunk.

    A chunk from the middle of "4. Refund eligibility" may never say "refund"; the header
    keeps its topic in the vector. The stored `content` stays clean for display.
    """
    if not heading_path:
        return content
    return " > ".join(heading_path) + "\n\n" + content
