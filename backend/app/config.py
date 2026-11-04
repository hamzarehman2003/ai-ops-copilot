from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5433/copilot"

    # Uploaded source files. Stored paths in the DB are relative to this directory.
    upload_dir: Path = Path("uploads")
    max_upload_bytes: int = 10 * 1024 * 1024

    # Local embedding / reranking models (downloaded once into model_cache_dir).
    model_cache_dir: Path = Path(".cache/models")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    warmup_models: bool = False  # load models at API start (on in Docker)

    # Retrieval. Defaults are justified (with eval numbers) in docs/rag-decisions.md.
    retrieval_mode: str = "hybrid_rerank"  # dense | lexical | hybrid | hybrid_rerank
    retrieval_k: int = 5  # chunks given to the LLM
    retrieval_candidates: int = 20  # per retriever, before fusion / reranking
    rrf_k: int = 60  # Reciprocal Rank Fusion constant
    rerank_top_n: int = 20  # only the best N fused candidates go through the cross-encoder
    min_rerank_score: float = -5.0  # below: "not relevant" (see rag-decisions.md)

    # LLM. Without an API key the copilot runs in "offline" mode (extractive, no generation).
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"
    llm_timeout_s: float = 90.0
    llm_max_tool_rounds: int = 4

    # Mock CRM behaviour (tools). Faults let tests/evals exercise timeouts and bad responses.
    crm_timeout_s: float = 2.0
    crm_max_retries: int = 2
    crm_latency_s: float = 0.0
    crm_fault: str = "none"  # none | timeout | error | malformed

    # Where evals/run_eval.py writes its reports (served by GET /api/evaluations/latest).
    eval_results_dir: Path = Path("../evals/results")

    # Browser origins allowed to call the API directly (the Next.js dev server).
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3002"]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
