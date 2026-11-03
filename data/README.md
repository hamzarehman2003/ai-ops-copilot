# Demo data

All content is **synthetic**. "Tasklane" is a fictional project-management SaaS.

This manifest lives outside `demo_docs/` on purpose so it is never ingested.

## demo_docs/

| File | Format | Purpose / what it tests |
|---|---|---|
| `pricing-and-plans.md` | Markdown | Current source of truth for plans, limits, SSO availability. Has a large table. |
| `legacy-pricing-faq-2024.md` | Markdown | **Outdated, conflicting** source (SSO on Pro, 30-day refunds, old prices/limits). Retrieval/answering must prefer current docs or flag the conflict. |
| `account-access-and-suspension.md` | Markdown | Account statuses and what members can do. Core doc for "why can't the customer access X?" questions. |
| `billing-and-refunds-policy.pdf` | PDF (2 pages) | Refund windows (14 days annual), failed payments, exceptions. Has running header/footer, a table, and a section that spans a page break. Regenerate with `backend/scripts/build_demo_pdf.py`. |
| `sso-setup-guide.html` | HTML | SSO setup steps and error codes (`SSO-401`…`SSO-429`). Has nav/footer/script boilerplate to strip. Error codes are a good lexical-search test. |
| `integrations-faq.html` | HTML | Integration availability per plan, Slack/GitHub/webhook troubleshooting. |
| `api-rate-limits.txt` | Plain text | Rate limits per plan, error codes. Uses ASCII-art headings (no Markdown structure). |
| `community-tips-export.txt` | Plain text | **Untrusted user content with a prompt-injection** in the "Refund question" thread. Must never change behavior or grant actions. |

## Deliberate conflicts (for eval cases)

| Topic | Current (correct) | Legacy 2024 FAQ (outdated) |
|---|---|---|
| SSO on Pro | No, Enterprise only | Yes |
| Pro price (annual) | $12/seat/month | $10/seat/month |
| Pro guests per project | 10 | 5 |
| Pro automation runs | 10,000/month, then paused | 5,000/month, then billed per run |
| Annual refund window | 14 days | 30 days |
| API rate limit (Pro) | 300 req/min | 120 req/min (all paid plans) |
