"""Generate the demo billing policy PDF in data/demo_docs/.

The PDF intentionally has a running header, a "Page X of Y" footer, and a table, so the
ingestion parser has realistic noise to deal with.

Usage (from backend/):  python scripts/build_demo_pdf.py
"""

import io
from pathlib import Path

import pymupdf

DEMO_DOCS = Path(__file__).resolve().parents[2] / "data" / "demo_docs"
OUT_PATH = DEMO_DOCS / "billing-and-refunds-policy.pdf"

HEADER = "Tasklane, Inc. (fictional)  |  Billing and Refund Policy  |  Internal & Customer-facing"

CSS = """
body { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 18pt; margin-bottom: 4pt; }
h2 { font-size: 13pt; margin-top: 14pt; margin-bottom: 4pt; }
p, li { margin-bottom: 5pt; }
table { border-collapse: collapse; margin: 6pt 0; }
th, td { border: 1px solid #999; padding: 3pt 6pt; font-size: 9.5pt; }
.meta { font-size: 9pt; color: #555; }
"""

HTML = """
<h1>Billing and Refund Policy</h1>
<p class="meta">Policy owner: Finance &amp; Billing Operations &middot; Version 5.0 &middot;
Effective date: 2026-01-01 &middot; Supersedes all previous refund FAQs</p>

<h2>1. Scope</h2>
<p>This policy applies to all paid Tasklane plans (Pro and Enterprise) purchased directly from
Tasklane. Purchases made through resellers or marketplaces follow the reseller's refund terms.</p>

<h2>2. Billing cycles</h2>
<p>Pro is available with monthly or annual billing. Enterprise is available with annual billing
only. Invoices are issued on the first day of each billing period and charged automatically to
the payment method on file. Enterprise customers may pay by bank transfer with net-30 terms.</p>
<p>Seat changes made during a billing period are prorated. Added seats are charged immediately
for the remainder of the period. Removed seats are credited to the next invoice; credits are
never paid out as cash.</p>

<h2>3. Failed payments</h2>
<p>If an automatic charge fails, the workspace enters the <b>past_due</b> status and Tasklane
retries the charge on days 1, 3, and 5. The grace period is 7 days. If no payment succeeds within
the grace period the workspace is <b>suspended</b> and becomes read-only until payment is
received. See the Account Status document for what members can do while suspended.</p>

<h2>4. Refund eligibility</h2>
<table>
  <tr><th>Plan and billing</th><th>Refund window</th><th>Refund type</th></tr>
  <tr><td>Pro, monthly</td><td>No refunds</td><td>Cancel anytime; access until period end</td></tr>
  <tr><td>Pro, annual</td><td>14 days from purchase or renewal</td><td>Full refund</td></tr>
  <tr><td>Pro, annual (after 14 days)</td><td>Not eligible</td>
      <td>Remaining term stays active</td></tr>
  <tr><td>Enterprise</td><td>Per signed order form</td><td>As contracted</td></tr>
  <tr><td>Unused seats</td><td>Any time</td><td>Account credit only</td></tr>
</table>
<p>Refunds are issued to the original payment method within 5&ndash;10 business days. A refund
cancels the subscription; the workspace returns to the Free plan immediately.</p>

<h2>5. Exceptions</h2>
<p>Support agents may <b>not</b> promise refunds outside the windows above. Requests for
exceptions (for example, a documented service outage longer than 24 hours) must be submitted to
the Billing team using the <i>refund-exception</i> ticket tag. Only Billing team leads can approve
an exception, and approval must be recorded on the ticket before the customer is informed.</p>
<p>Duplicate charges caused by a Tasklane billing error are always refunded in full, regardless
of the refund window.</p>

<h2>6. Taxes</h2>
<p>Prices exclude VAT, GST, and sales tax. Tax is calculated from the billing address on file.
Customers with a valid tax exemption certificate must upload it before the invoice is issued;
tax already charged is not refunded retroactively.</p>

<h2>7. Changing the payment method</h2>
<p>Only workspace Owners can update the payment method, under Settings &rarr; Billing. Support
agents can send a secure payment-update link but must never ask customers to share card numbers
in a ticket, chat, or email.</p>

<h2>8. Chargebacks</h2>
<p>If a customer files a chargeback, the workspace is moved to <b>locked</b> status while the
dispute is reviewed. Support agents must route chargeback tickets to the Billing team and must not
discuss the dispute outcome with the customer.</p>

<h2>9. Contact</h2>
<p>Billing questions: billing@tasklane.example. Enterprise contract questions: contact the
assigned account manager.</p>
"""


def render_story() -> bytes:
    story = pymupdf.Story(html=HTML, user_css=CSS)
    out = io.BytesIO()
    writer = pymupdf.DocumentWriter(out)
    mediabox = pymupdf.paper_rect("a4")
    content_area = mediabox + (56, 64, -56, -64)

    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(content_area)
        story.draw(device)
        writer.end_page()
    writer.close()
    return out.getvalue()


def add_header_footer(pdf_bytes: bytes) -> pymupdf.Document:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    for i, page in enumerate(doc, start=1):
        width = page.rect.width
        page.insert_text((56, 36), HEADER, fontsize=7.5, color=(0.4, 0.4, 0.4))
        footer = f"Page {i} of {total}"
        page.insert_text((width - 56 - 50, page.rect.height - 30), footer, fontsize=8)
    doc.set_metadata(
        {"title": "Tasklane Billing and Refund Policy", "author": "Tasklane (fictional)"}
    )
    return doc


def main() -> None:
    doc = add_header_footer(render_story())
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_PATH, garbage=3, deflate=True)
    print(f"Wrote {OUT_PATH} ({doc.page_count} pages)")


if __name__ == "__main__":
    main()
