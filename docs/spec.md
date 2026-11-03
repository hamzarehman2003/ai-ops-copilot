# Project 2 — AI Operations Copilot: RAG, Agents & LLM Integrations

## Purpose
Build a web application for a fictional B2B SaaS company. A support or operations user asks about a customer issue; the copilot retrieves relevant product documentation and ticket history, checks account state through controlled tools, drafts a response with citations, and proposes an action for human approval.

**Primary Fiverr gig:** Custom AI Agents, RAG Chatbots & LLM Applications  
**Target clients:** SaaS startups, software agencies, customer-support teams, and businesses that need internal knowledge assistants or AI features in existing products.

## 1. Problem this project solves
A basic chatbot can answer questions from documents but may lack current account context, trustworthy citations, access control, and safe interaction with business systems. This project demonstrates retrieval, tool calling, permissions, human approval, and measurable evaluation in one application.

## 2. MVP user journey
1. Admin uploads fictional product documentation, policies, FAQs, and synthetic support tickets.
2. Ingestion parses the files, chunks content, adds metadata, generates embeddings, and indexes the content.
3. Support user asks a question about a fictional customer.
4. Copilot retrieves relevant sources and shows source snippets.
5. When necessary, it calls authorized read-only tools such as `get_account_status` or `get_recent_tickets`.
6. It drafts an answer with citations and explicitly signals missing evidence.
7. It proposes a ticket note, tag, or CRM update.
8. A human reviews, edits, approves, or rejects the proposed action.
9. The approved action executes against a mock support/CRM API.
10. Traces and evaluation results are available for inspection.

## 3. Functional requirements

### Must-have
- Upload PDF, Markdown, HTML, and text knowledge sources.
- Parse, normalize, chunk, embed, and index documents.
- Store source metadata, version, and ingestion status.
- Implement vector search with metadata filtering; optional hybrid lexical/vector retrieval.
- Display citations linked to source snippets.
- Abstain or request clarification when the available evidence is insufficient.
- Provide a synthetic customer/account/ticket dataset.
- Implement read-only tools for account status and recent tickets.
- Implement proposed write actions with explicit human approval before execution.
- Enforce user roles and customer/tenant boundaries on the server.
- Record retrieval traces, tool calls, approval decisions, and action outcomes.
- Include a repeatable evaluation dataset and evaluation script.
- Provide a clean dashboard for chat, source viewing, and pending actions.

### Should-have
- Feedback controls for helpful/unhelpful answers.
- Source versioning and re-indexing.
- Document freshness indicator.
- Retrieval threshold configuration and optional reranking.
- CSV/JSON export of evaluation results.
- Prompt/model/index version metadata for reproducibility.

### Stretch goals
- Real CRM or ticketing integration behind adapters.
- Slack/Teams interface.
- SSO and advanced permission policies.
- Background source sync and change detection.
- More complex multi-step workflows using LangGraph.

## 4. Non-functional requirements
- Authorization must be enforced in the backend, not only in the UI.
- Prevent cross-customer or cross-tenant retrieval.
- Never invent account status or claim an action succeeded unless the tool confirms it.
- Factual answers should cite evidence or clearly state uncertainty.
- Write actions require an approved action record in the portfolio version.
- Retrieved content is untrusted data; instructions embedded in documents must not override system policy or grant permissions.
- Apply timeouts, bounded retries, and idempotency to tools.
- Avoid storing sensitive real customer data; use synthetic data for the public demo.

## 5. Recommended technology stack

### Core
- **Frontend:** Next.js, React, TypeScript, Tailwind CSS.
- **Backend:** Python, FastAPI, Pydantic.
- **Database:** PostgreSQL, SQLAlchemy, Alembic.
- **Vector search:** pgvector to start.
- **LLM:** one provider API behind a small adapter; implement structured outputs and tool calling.
- **RAG/agent framework:** start with direct API calls or LangChain for retrieval/model integrations; use LangGraph only for workflows that need explicit state, branching, retries, or human approval.
- **Parsing:** PyMuPDF for PDF, BeautifulSoup for HTML, standard Markdown/text parsing.
- **Jobs:** a background worker for ingestion and re-indexing.
- **Testing:** pytest, API integration tests, Playwright for key browser flows.
- **Deployment:** Docker Compose.

### Observability and evaluation
Choose one initially:
- **Langfuse** for LLM traces, prompt/version tracking, cost and latency.
- **LangSmith** if you use LangChain/LangGraph heavily and want integrated tracing/evaluation.
- **Ragas** as an optional framework for RAG evaluation.
- Plain Python evaluation scripts should remain the source of repeatable test results.

### Optional integration layer
- **n8n:** trigger workflows or send notifications after an approved action.
- **HubSpot or another CRM API:** add only after the mock integration is reliable.
- **Slack API:** notify a support channel as a stretch goal.

Do not add multiple vector databases or multiple agent frameworks to the first version.

## 6. Architecture
1. **Web client:** chat, citations, source viewer, action approval, evaluation view.
2. **Ingestion service:** parse, normalize, chunk, embed, and index sources.
3. **Retrieval module:** query rewriting if needed, metadata filtering, vector/optional lexical retrieval, source ranking.
4. **Answer module:** generate grounded answers with citations and an abstention path.
5. **Tool registry:** typed schemas, authorization, timeouts, and allow-listed operations.
6. **Approval/action service:** store proposed actions and execute only after approval.
7. **Database:** users, sources, chunks, conversations, tool traces, actions, and evaluations.
8. **Observability:** traces, token/cost estimates, latency, errors, and evaluation runs.

Treat document contents as data, not instructions. Keep business permissions in backend code rather than relying on prompt wording.

## 7. Suggested data model
- `Workspace`, `User`, `Role`
- `SourceDocument`, `DocumentVersion`, `Chunk`
- `Conversation`, `Message`
- `RetrievalTrace` — query, source IDs, scores, index/model version.
- `ToolCall` — tool name, validated arguments, status, latency, error code.
- `ProposedAction` — action type, payload, approval status, approver.
- `AuditEvent`
- `EvaluationCase`, `EvaluationRun`

## 8. API outline
- `POST /api/sources` — upload source.
- `POST /api/sources/{id}/reindex` — reprocess source.
- `POST /api/copilot/query` — submit a question.
- `GET /api/sources/{id}/chunks` — authorized source preview.
- `GET /api/customers/{id}/tickets` — mock tool-backed lookup.
- `POST /api/actions/{id}/approve` — approve a proposed action.
- `POST /api/actions/{id}/reject` — reject a proposed action.
- `GET /api/evaluations/latest` — latest evaluation report.

## 9. Evaluation plan
Create 80–150 test questions based on the synthetic knowledge base. Include:
- Questions with one clear authoritative answer.
- Questions requiring multiple sources.
- Unanswerable questions.
- Conflicting or outdated sources.
- Cross-customer authorization attempts.
- Prompt-injection text inside a retrieved document.
- Requests for unauthorized actions.
- Tool timeout and malformed tool-response cases.

Measure:
- Retrieval Recall@k / Precision@k or another documented metric.
- Citation coverage and citation correctness.
- Answer correctness against a written rubric.
- Unsupported-claim rate.
- Appropriate abstention rate.
- Unauthorized data exposure/actions (target: zero in tests).
- Tool success rate and latency.
- Human approval, edit, and rejection rate.

Run evaluations from a script against a held-out test set. Do not invent performance numbers for the portfolio page.

## 10. Acceptance criteria
- [ ] Answers display source citations and snippets.
- [ ] Unanswerable questions can be declined instead of guessed.
- [ ] Customer/tenant scope is enforced for retrieval and tools.
- [ ] No write action executes without an approved action record.
- [ ] Retrieved prompt-injection text cannot grant permissions or change tool policy.
- [ ] Evaluation can be rerun from documented commands.
- [ ] Model, prompt, and index versions are recorded for evaluation runs.
- [ ] Demo uses synthetic data and is reproducible through Docker Compose.
- [ ] README includes architecture, setup, evaluation, limitations, and demo instructions.

## 11. Repository structure
```text
ai-operations-copilot/
  apps/web/
  services/api/
  services/ingestion/
  packages/retrieval/
  packages/tool_registry/
  evals/
    cases.jsonl
    run_eval.py
  data/demo_docs/
  docs/architecture.md
  docker-compose.yml
  .env.example
  README.md
```

## 12. Suggested two-engineer plan
- **Days 1–2:** define fictional SaaS domain, write demo docs/tickets, create UI/API skeleton.
- **Days 3–4:** ingestion, chunking, pgvector retrieval, citations.
- **Days 5–6:** mock tools, access control, action proposal/approval.
- **Days 7–8:** evaluation set, tracing, security tests, error handling.
- **Days 9–10:** deployment, polish, walkthrough video, architecture and evaluation documentation.

## 13. Demo script
Ask why a fictional customer cannot access a feature. Show citations to a product policy and ticket, then call a mock account-status tool. Draft a customer response and propose a ticket update. Approve it and show the audit event. Finally, demonstrate an unanswerable question and an attempted cross-customer query.

## 14. Fiverr service mapping
This project supports services such as:
- Custom RAG chatbots over business documents.
- Knowledge-base and support assistants.
- AI agents with bounded tool calling.
- LLM API integrations in existing applications.
- LangChain/LangGraph workflow implementation.
- AI assistant prototypes with evaluation and deployment.

Keep the gig promise specific to the buyer's use case. Don't market this as “any AI app” or promise perfect answers.

## 15. Scope limits
Start with one fictional SaaS domain, a single LLM provider adapter, PostgreSQL/pgvector, and a small set of mock tools. Add real CRM integrations only after retrieval, permissions, and approval workflows are reliable.
