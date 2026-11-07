from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    # A version claimed for processing longer ago than this is assumed dead (crash mid-ingest)
    # and can be reindexed again.
    ingestion_stale_after_s: int = 900
    # Follow-ups are searched together with the previous question (retrieval/query.py).
    retrieval_follow_up_context: bool = True

    # LLM. Without an API key the copilot runs in "offline" mode (extractive, no generation).
    # llm_provider: "anthropic" (Messages API) or "openai" = any OpenAI-compatible Chat
    # Completions endpoint (Gemini, Ollama, Groq, OpenAI...) at llm_base_url with llm_api_key.
    llm_provider: str = "anthropic"
    anthropic_api_key: str | None = None
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    llm_api_key: str | None = None  # Ollama ignores it, but set any non-empty value
    llm_model: str = "claude-opus-5-5"
    # OpenAI-compatible only: comma-separated models tried in order when llm_model is out of
    # quota or overloaded (free tiers have small per-model daily quotas).
    llm_fallback_models: str = ""
    # OpenAI-compatible only: false for servers whose JSON-schema mode blocks tool calls
    # (Ollama: constrained decoding leaves the model no way to emit a tool call).
    llm_schema_with_tools: bool = True
    # OpenAI-compatible only, unset = provider default. Local models: a lower temperature makes
    # tool use steadier, and a token cap stops a runaway generation before the timeout does.
    llm_temperature: float | None = None
    llm_max_output_tokens: int | None = None
    llm_effort: str = "medium"  # "" = don't send an effort/reasoning setting
    llm_timeout_s: float = 90.0
    llm_max_retries: int = 3  # 429 / 5xx / timeouts (free tiers rate-limit often)
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

    @field_validator("llm_temperature", "llm_max_output_tokens", mode="before")
    @classmethod
    def _empty_is_unset(cls, value: object) -> object:
        return None if value == "" else value  # Compose passes unset variables as ""

    @property
    def llm_enabled(self) -> bool:
        if self.llm_provider == "openai":
            return bool(self.llm_api_key)
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
