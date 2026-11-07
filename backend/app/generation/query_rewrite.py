"""Second-chance retrieval: when the first search is weak, rewrite the question into the
documentation's vocabulary and search again.

Users describe symptoms in their own words ("get my money back", "our chat app"); the docs say
"refund", "Slack integration". Dense + lexical retrieval and the cross-encoder all struggle when
no words overlap: the right chunk either never reaches the top candidates or is reranked below
the relevance threshold, and the copilot (correctly) abstains with nothing to cite.

So, only when the best reranked chunk scores below `query_rewrite_below_score`, one cheap LLM
call turns the question into 1-3 search queries in documentation terms; each is searched, and
results are merged keeping each chunk's best score. Strong searches pay nothing; offline mode
(no LLM) is unchanged. The model still answers the user's own question, and every check
(threshold, citations) applies to what the rewrites found.
"""

import json

from app.generation.llm import LLM, LLMError
from app.retrieval.search import RetrievalResult

REWRITE_SYSTEM = """\
You turn a customer-support question about a B2B SaaS product into search queries for the \
product's help center (plans and pricing, billing and refunds, account status and access, \
single sign-on, integrations, API limits, automations).

Write 1 to 3 short search queries that use the words such documentation would use: feature \
names, policy names, statuses and error terms, instead of the user's own wording. Cover the \
most likely meanings if the question is ambiguous. Don't answer the question.
"""

REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "queries": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["queries"],
    "additionalProperties": False,
}


def is_weak(result: RetrievalResult, below_score: float) -> bool:
    """No reranked chunk passed the threshold, or the best one scores below `below_score`."""
    if not any(c.rerank_score is not None for c in result.candidates):
        return False  # not a reranking mode (or nothing indexed): nothing to judge by
    kept = [c.rerank_score for c in result.chunks if c.rerank_score is not None]
    return not kept or max(kept) < below_score


def rewrite_queries(llm: LLM, question: str) -> list[str]:
    """1-3 documentation-style queries; [] if the model fails (the first search stands)."""
    try:
        turn = llm.turn(
            system=REWRITE_SYSTEM,
            messages=[{"role": "user", "content": question}],
            tools=[],
            output_schema=REWRITE_SCHEMA,
        )
        queries = json.loads(turn.text).get("queries", [])
    except (LLMError, json.JSONDecodeError, AttributeError):
        return []
    clean = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
    return [q for q in dict.fromkeys(clean) if q.lower() != question.lower()][:3]


def merge(first: RetrievalResult, others: list[RetrievalResult], k: int) -> RetrievalResult:
    """Union of the results, each chunk with its best rerank score, top k."""
    best = {}
    for result in (first, *others):
        for chunk in result.chunks:
            current = best.get(chunk.chunk_id)
            if current is None or (chunk.rerank_score or 0) > (current.rerank_score or 0):
                best[chunk.chunk_id] = chunk
    chunks = sorted(best.values(), key=lambda c: c.rerank_score or float("-inf"), reverse=True)
    return RetrievalResult(
        query=first.query,
        mode=first.mode,
        chunks=chunks[:k],
        candidates=first.candidates,
        latency_ms=first.latency_ms + sum(o.latency_ms for o in others),
        params={**first.params, "rewritten_queries": [o.query for o in others]},
        trace_id=first.trace_id,
    )
