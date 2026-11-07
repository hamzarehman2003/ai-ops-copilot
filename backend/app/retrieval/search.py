"""Hybrid retrieval: dense (pgvector) + lexical (Postgres full-text) -> RRF -> reranker.

    query ─┬─ dense:   ORDER BY embedding <=> q   (meaning, paraphrases)   ─┐
           └─ lexical: ts_rank_cd(search_vector)  (exact terms, codes, IDs) ─┴─ RRF ─ rerank ─ top k

Security: the tenant filter (`workspace_id`) and the "current version only" filter are part of
every SQL query, never applied to results afterwards (CLAUDE.md rule 2). Deprecated documents
(superseded content) are filtered out the same way.

Modes (for evals and debugging): dense | lexical | hybrid | hybrid_rerank.
"""

import re
import time
import uuid
from dataclasses import asdict, dataclass, field

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.ingestion.embeddings import Embedder, embedding_text, get_embedder
from app.models import Chunk, DocumentVersion, RetrievalTrace, SourceDocument
from app.retrieval.reranker import Reranker, get_reranker

MODES = ("dense", "lexical", "hybrid", "hybrid_rerank")
_WORD = re.compile(r"[A-Za-z0-9_]+")


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    filename: str
    version_number: int
    heading_path: list[str]
    content: str
    page_start: int | None
    page_end: int | None
    dense_rank: int | None = None  # 1-based rank in each retriever (None = not found by it)
    lexical_rank: int | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None


@dataclass
class RetrievalResult:
    query: str
    mode: str
    chunks: list[RetrievedChunk]  # final top k, best first
    candidates: list[RetrievedChunk] = field(default_factory=list)  # everything scored
    latency_ms: int = 0
    params: dict = field(default_factory=dict)
    trace_id: uuid.UUID | None = None


def retrieve(
    session: Session,
    workspace_id: uuid.UUID,
    query: str,
    settings: Settings,
    *,
    mode: str | None = None,
    k: int | None = None,
    apply_threshold: bool = True,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    message_id: uuid.UUID | None = None,
    save_trace: bool = True,
) -> RetrievalResult:
    mode = mode or settings.retrieval_mode
    if mode not in MODES:
        raise ValueError(f"Unknown retrieval mode {mode!r}; expected one of {MODES}")
    k = k or settings.retrieval_k
    n = settings.retrieval_candidates
    started = time.perf_counter()

    dense_ids: list[uuid.UUID] = []
    lexical_ids: list[uuid.UUID] = []
    if mode != "lexical":
        dense_ids = _dense_search(session, workspace_id, query, n, embedder or get_embedder())
    if mode != "dense":
        lexical_ids = _lexical_search(session, workspace_id, query, n)

    fused = _reciprocal_rank_fusion([dense_ids, lexical_ids], settings.rrf_k)
    candidates = _load(session, workspace_id, list(fused))
    for chunk in candidates:
        chunk.rrf_score = fused[chunk.chunk_id]
        chunk.dense_rank = _rank_of(chunk.chunk_id, dense_ids)
        chunk.lexical_rank = _rank_of(chunk.chunk_id, lexical_ids)
    candidates.sort(key=lambda c: c.rrf_score, reverse=True)

    if mode == "hybrid_rerank" and candidates:
        # The cross-encoder is the slow step (one model pass per pair), so it only sees the
        # best `rerank_top_n` fused candidates.
        candidates = candidates[: settings.rerank_top_n]
        reranker = reranker or get_reranker()
        scores = reranker.score(
            query, [embedding_text(c.heading_path, c.content) for c in candidates]
        )
        for chunk, score in zip(candidates, scores, strict=True):
            chunk.rerank_score = score
        candidates.sort(key=lambda c: c.rerank_score, reverse=True)

    top = candidates[:k]
    if apply_threshold and mode == "hybrid_rerank":
        # Nothing clearly relevant -> return nothing, so the answer step abstains.
        top = [c for c in top if c.rerank_score >= settings.min_rerank_score]

    result = RetrievalResult(
        query=query,
        mode=mode,
        chunks=top,
        candidates=candidates,
        latency_ms=int((time.perf_counter() - started) * 1000),
        params={
            "mode": mode,
            "k": k,
            "candidates_per_retriever": n,
            "rrf_k": settings.rrf_k,
            "rerank_top_n": settings.rerank_top_n if mode == "hybrid_rerank" else None,
            "min_rerank_score": settings.min_rerank_score if apply_threshold else None,
            "embedding_model": settings.embedding_model if mode != "lexical" else None,
            "reranker_model": settings.reranker_model if mode == "hybrid_rerank" else None,
        },
    )
    if save_trace:
        result.trace_id = _save_trace(session, workspace_id, result, message_id)
    return result


def _dense_search(
    session: Session, workspace_id: uuid.UUID, query: str, n: int, embedder: Embedder
) -> list[uuid.UUID]:
    query_vector = embedder.embed_query(query)
    # With a WHERE filter, a plain HNSW scan may return fewer than n rows (it finds the
    # nearest vectors first, then filters). pgvector 0.8 iterative scans keep searching.
    session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
    session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    distance = Chunk.embedding.cosine_distance(query_vector)
    return list(
        session.scalars(
            select(Chunk.id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
            .join(SourceDocument, SourceDocument.id == DocumentVersion.document_id)
            .where(
                Chunk.workspace_id == workspace_id,
                DocumentVersion.is_current.is_(True),
                SourceDocument.deprecated.is_(False),
                Chunk.embedding.is_not(None),
                # Vectors from different models aren't comparable, even at the same size
                # (bge-small and all-MiniLM are both 384-d): only the current model's count.
                Chunk.embedding_model == embedder.model_name,
            )
            .order_by(distance)
            .limit(n)
        )
    )


def _lexical_search(
    session: Session, workspace_id: uuid.UUID, query: str, n: int
) -> list[uuid.UUID]:
    # OR the words: natural questions rarely contain *all* their words in one chunk (AND, the
    # default of plainto/websearch_to_tsquery). ts_rank_cd still prefers chunks with more.
    # Only [A-Za-z0-9_] words reach to_tsquery, so its syntax can't be injected.
    words = _WORD.findall(query)
    if not words:
        return []
    tsquery = func.to_tsquery("english", " | ".join(words))
    rank = func.ts_rank_cd(Chunk.search_vector, tsquery)
    return list(
        session.scalars(
            select(Chunk.id)
            .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
            .join(SourceDocument, SourceDocument.id == DocumentVersion.document_id)
            .where(
                Chunk.workspace_id == workspace_id,
                DocumentVersion.is_current.is_(True),
                SourceDocument.deprecated.is_(False),
                Chunk.search_vector.op("@@")(tsquery),
            )
            .order_by(rank.desc())
            .limit(n)
        )
    )


def _reciprocal_rank_fusion(rankings: list[list[uuid.UUID]], k: int) -> dict[uuid.UUID, float]:
    """score(d) = sum over lists of 1 / (k + rank). Uses ranks only, so the very different
    score scales of cosine distance and ts_rank never need to be normalized."""
    scores: dict[uuid.UUID, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def _rank_of(chunk_id: uuid.UUID, ranking: list[uuid.UUID]) -> int | None:
    try:
        return ranking.index(chunk_id) + 1
    except ValueError:
        return None


def _load(
    session: Session, workspace_id: uuid.UUID, chunk_ids: list[uuid.UUID]
) -> list[RetrievedChunk]:
    if not chunk_ids:
        return []
    rows = session.execute(
        select(Chunk, DocumentVersion.version_number, SourceDocument)
        .join(DocumentVersion, DocumentVersion.id == Chunk.document_version_id)
        .join(SourceDocument, SourceDocument.id == DocumentVersion.document_id)
        .where(Chunk.id.in_(chunk_ids), Chunk.workspace_id == workspace_id)
    )
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=document.id,
            document_title=document.title,
            filename=document.filename,
            version_number=version_number,
            heading_path=list(chunk.heading_path),
            content=chunk.content,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk, version_number, document in rows
    ]


def _save_trace(
    session: Session,
    workspace_id: uuid.UUID,
    result: RetrievalResult,
    message_id: uuid.UUID | None,
) -> uuid.UUID:
    final = {c.chunk_id for c in result.chunks}
    trace = RetrievalTrace(
        workspace_id=workspace_id,
        message_id=message_id,
        query=result.query,
        params=result.params,
        results=[
            {
                "chunk_id": str(c.chunk_id),
                "filename": c.filename,
                "heading": " > ".join(c.heading_path),
                "dense_rank": c.dense_rank,
                "lexical_rank": c.lexical_rank,
                "rrf_score": round(c.rrf_score, 5),
                "rerank_score": None if c.rerank_score is None else round(c.rerank_score, 3),
                "selected": c.chunk_id in final,
            }
            for c in result.candidates
        ],
        latency_ms=result.latency_ms,
    )
    session.add(trace)
    session.flush()
    return trace.id


def chunk_to_dict(chunk: RetrievedChunk) -> dict:
    data = asdict(chunk)
    data["chunk_id"] = str(chunk.chunk_id)
    data["document_id"] = str(chunk.document_id)
    return data
