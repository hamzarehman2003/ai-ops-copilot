# Tasklane Plans and Pricing

**Document owner:** Revenue Operations
**Version:** 4.2
**Effective date:** 2026-01-01
**Supersedes:** All earlier pricing pages and pricing FAQs

Tasklane is offered in three plans: **Free**, **Pro**, and **Enterprise**. Prices are per seat
(one seat = one full member). Guests do not consume seats but are limited per plan.

## Plan comparison

| Feature                     | Free          | Pro                 | Enterprise           |
|-----------------------------|---------------|---------------------|----------------------|
| Price (billed annually)     | $0            | $12 / seat / month  | Custom (min. 50 seats) |
| Price (billed monthly)      | $0            | $15 / seat / month  | Not available        |
| Maximum seats               | 5             | 500                 | Unlimited            |
| Active projects             | 3             | Unlimited           | Unlimited            |
| Storage per workspace       | 2 GB          | 100 GB              | 5 TB                 |
| Guests                      | 0             | 10 per project      | Unlimited            |
| Automation runs / month     | 100           | 10,000              | 250,000              |
| API rate limit              | 60 req/min    | 300 req/min         | 1,000 req/min        |
| Single sign-on (SAML SSO)   | No            | No                  | Yes                  |
| SCIM user provisioning      | No            | No                  | Yes                  |
| Audit log                   | No            | 30-day retention    | 1-year retention, export |
| Custom roles                | No            | No                  | Yes                  |
| Support                     | Community     | Email, 1 business day | 24/7, named CSM    |

## Feature availability notes

### Single sign-on
SAML single sign-on is available **only on the Enterprise plan**. Pro workspaces can use
Google or Microsoft social login, but cannot enforce SSO or connect a custom identity provider
(Okta, Azure AD / Entra ID, OneLogin). Workspaces that downgrade from Enterprise to Pro lose SSO
at the end of the current billing period; members must then sign in with email and password or
social login.

### Guests
Guests can view and comment on tasks in projects they are invited to. Guests cannot create
projects, see workspace-level reports, or install integrations. On Pro, each project can have up
to 10 guests. Inviting an 11th guest returns the error `GUEST_LIMIT_REACHED`.

### Automation runs
An automation run is counted each time a rule's trigger fires and at least one action executes.
When a workspace exceeds its monthly automation quota, rules are paused until the next calendar
month or until the workspace upgrades. Paused rules show the status **Quota exceeded**.

### Storage
When storage is full, uploads fail with `STORAGE_LIMIT_REACHED`. Existing files remain
accessible. Deleting files from the trash frees space within 15 minutes.

## Upgrades and downgrades

- **Upgrades** take effect immediately. The price difference is prorated for the rest of the
  billing period.
- **Downgrades** take effect at the end of the current billing period. Features not included in
  the lower plan become unavailable at that time; data is retained but may become read-only.
- Downgrading from Pro to Free when the workspace has more than 3 active projects archives the
  least recently updated projects until 3 remain. Archived projects can be restored after
  upgrading again.

## Enterprise trials

Enterprise trials last 30 days and include SSO and SCIM. When a trial ends without a purchase,
the workspace returns to its previous plan and SSO enforcement is switched off automatically.
