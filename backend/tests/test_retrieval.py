from pathlib import Path

import pytest
from sqlalchemy import func, select
from tokenizers import Tokenizer

from app.ingestion.embeddings import MAX_INPUT_TOKENS, embedding_text
from app.ingestion.pipeline import process_version
from app.ingestion.upload import register_upload
from app.models import Chunk, DocumentVersion, IngestionStatus, RetrievalTrace, SourceDocument
from app.retrieval.search import retrieve

TASKLANE = "tasklane-support"


def search(indexed, query: str, slug: str = TASKLANE, **kwargs):
    workspace = indexed.workspace(slug)
    return retrieve(indexed.session, workspace.id, query, indexed.settings, **kwargs)


def files(result) -> list[str]:
    return [c.filename for c in result.chunks]


# --- Pipeline --------------------------------------------------------------------------------


def test_every_demo_document_is_indexed(indexed):
    versions = indexed.session.scalars(select(DocumentVersion)).all()
    assert len(versions) == 9  # 8 Tasklane docs + 1 Acme doc
    assert all(v.status == IngestionStatus.READY and v.is_current for v in versions)

    chunks = indexed.session.scalars(select(Chunk)).all()
    assert all(len(c.embedding) == 384 for c in chunks)
    assert {c.embedding_model for c in chunks} == {"BAAI/bge-small-en-v1.5"}
    assert all(c.heading_text == " > ".join(c.heading_path) for c in chunks)


def test_no_chunk_is_truncated_by_the_embedding_model(indexed):
    """The embedder silently cuts input after 512 of *its* tokens (not tiktoken's)."""
    cache = Path(indexed.settings.model_cache_dir)
    tokenizer = Tokenizer.from_file(
        str(next(cache.glob("*bge-small-en-v1.5*/snapshots/*/tokenizer.json")))
    )
    tokenizer.no_truncation()
    for chunk in indexed.session.scalars(select(Chunk)):
        tokens = len(tokenizer.encode(embedding_text(chunk.heading_path, chunk.content)).ids)
        assert tokens <= MAX_INPUT_TOKENS, (chunk.heading_text, tokens)


def test_new_version_replaces_old_one_in_search(indexed):
    workspace = indexed.workspace(TASKLANE)
    data = b"# Tasklane Pricing FAQ\n\n## Refunds\n\nRefunds are processed by carrier pigeon.\n"
    result = register_upload(
        indexed.session,
        workspace,
        "legacy-pricing-faq-2024.md",
        data,
        indexed.settings.upload_dir,
    )
    process_version(indexed.session, result.version.id, indexed.settings)

    document = result.version.document
    current = [v.version_number for v in document.versions if v.is_current]
    assert current == [2]
    found = search(indexed, "carrier pigeon", mode="lexical")
    assert files(found)[0] == "legacy-pricing-faq-2024.md"
    assert all("30 days" not in c.content for c in found.chunks if c.filename == document.filename)


def test_failed_processing_keeps_previous_version_serving(indexed):
    workspace = indexed.workspace(TASKLANE)
    result = register_upload(
        indexed.session,
        workspace,
        "integrations-faq.html",
        b"<html><body></body></html>",
        indexed.settings.upload_dir,
    )
    version = process_version(indexed.session, result.version.id, indexed.settings)

    assert version.status == IngestionStatus.FAILED
    assert "No extractable text" in version.error_message
    assert not version.is_current
    assert "integrations-faq.html" in files(search(indexed, "webhook deliveries failing"))


# --- Retrieval -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected_file",
    [
        ("Can I get a refund on a yearly subscription?", "billing-and-refunds-policy.pdf"),
        ("What does error SSO-401 mean?", "sso-setup-guide.html"),
        ("Why can't a suspended workspace create tasks?", "account-access-and-suspension.md"),
        ("How many API requests per minute on Pro?", "api-rate-limits.txt"),
        ("Is SAML single sign-on available on the Pro plan?", "pricing-and-plans.md"),
    ],
)
def test_hybrid_rerank_finds_the_right_document(indexed, query, expected_file):
    assert expected_file in files(search(indexed, query))[:3]


def test_lexical_search_is_exact_on_codes(indexed):
    result = search(indexed, "SSO-409", mode="lexical", k=1)
    assert "SSO-409" in result.chunks[0].content


def test_retrieval_never_crosses_tenants(indexed):
    tasklane = search(indexed, "escalation code ORCHID-7 for a P1 incident", apply_threshold=False)
    assert all(c.filename != "acme-escalation-runbook.md" for c in tasklane.candidates)

    acme = search(indexed, "escalation code ORCHID-7 for a P1 incident", slug="acme-demo")
    assert files(acme) and set(files(acme)) == {"acme-escalation-runbook.md"}


def test_old_versions_are_never_retrieved(indexed):
    workspace = indexed.workspace(TASKLANE)
    data = b"# Tasklane Pricing FAQ\n\nEverything is free forever.\n"
    result = register_upload(
        indexed.session,
        workspace,
        "legacy-pricing-faq-2024.md",
        data,
        indexed.settings.upload_dir,
    )
    process_version(indexed.session, result.version.id, indexed.settings)
    found = search(indexed, "Pro guests per project 5 guests", apply_threshold=False)
    old_text = "Pro workspaces can invite up to 5 guests per project"
    assert all(old_text not in c.content for c in found.candidates)


def test_unrelated_question_returns_nothing_after_threshold(indexed):
    assert search(indexed, "What is the boiling point of water on Mars?").chunks == []


def test_trace_records_candidates_and_scores(indexed):
    result = search(indexed, "grace period for failed payments")
    trace = indexed.session.get(RetrievalTrace, result.trace_id)
    assert trace.params["mode"] == "hybrid_rerank"
    selected = [r for r in trace.results if r["selected"]]
    assert len(selected) == len(result.chunks)
    assert all(r["rerank_score"] is not None for r in trace.results)


def test_document_count_per_workspace(indexed):
    count = indexed.session.scalar(
        select(func.count())
        .select_from(SourceDocument)
        .where(SourceDocument.workspace_id == indexed.workspace(TASKLANE).id)
    )
    assert count == 8


def test_deprecated_documents_are_filtered_inside_the_query(indexed):
    question = "Is single sign-on included in the Pro plan?"
    before = search(indexed, question, apply_threshold=False)
    assert "legacy-pricing-faq-2024.md" in [c.filename for c in before.candidates]

    legacy = indexed.session.scalar(
        select(SourceDocument).where(SourceDocument.filename == "legacy-pricing-faq-2024.md")
    )
    legacy.deprecated = True
    indexed.session.flush()

    for mode in ("dense", "lexical", "hybrid_rerank"):
        after = search(indexed, question, mode=mode, apply_threshold=False)
        assert "legacy-pricing-faq-2024.md" not in [c.filename for c in after.candidates]


def test_dense_search_ignores_vectors_from_another_embedding_model(indexed):
    """Same dimensions, different model: not comparable, so not searched."""
    sso_chunks = indexed.session.scalars(
        select(Chunk).where(Chunk.content.contains("SSO-401"))
    ).all()
    for chunk in sso_chunks:
        chunk.embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
    indexed.session.flush()
    result = search(indexed, "What does error SSO-401 mean?", mode="dense", apply_threshold=False)
    assert all("SSO-401" not in c.content for c in result.candidates)
