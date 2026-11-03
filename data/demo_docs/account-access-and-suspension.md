# Account Status, Suspension, and Access

**Document owner:** Support Operations
**Version:** 2.1
**Effective date:** 2025-09-15

This document explains the account statuses a Tasklane workspace can have and what members can
do in each one. Support agents should always confirm the current status with the account tools
before explaining access problems to a customer.

## Workspace statuses

| Status       | Meaning                                              | Member access                      |
|--------------|------------------------------------------------------|------------------------------------|
| `active`     | Subscription is current                              | Full access for the plan           |
| `trialing`   | In a free trial of a paid plan                       | Full access for the trial plan     |
| `past_due`   | Latest payment failed; in grace period               | Full access, billing banner shown  |
| `suspended`  | Grace period ended without payment                   | Read-only; no new tasks or uploads |
| `cancelled`  | Subscription cancelled and period ended              | Read-only for 90 days, then deleted |
| `locked`     | Locked by Trust & Safety or by security review       | No access; owners see contact link |

## Past due and grace period

When a renewal payment fails, the workspace moves to `past_due`. Tasklane retries the card on
days 1, 3, and 5. The grace period lasts **7 days** from the first failed attempt. During the
grace period, all features keep working, but workspace owners see a billing banner.

## Suspension

If payment is not recovered by the end of the grace period, the workspace becomes `suspended`.
In a suspended workspace:

- Members can sign in and view projects, tasks, and files.
- Members cannot create or edit tasks, upload files, or run automations.
- Integrations (Slack, GitHub, Jira) stop syncing.
- SSO continues to work for Enterprise workspaces so that members can still sign in.

Suspension is lifted automatically within 10 minutes of a successful payment. Support agents
cannot lift a suspension manually; they can only send the customer a payment-update link.

## Seat limits

If a workspace has more members than paid seats (for example after an admin removes seats),
the newest members over the limit are marked **Inactive — seat limit**. They cannot sign in
until an admin adds seats or removes other members.

## Locked workspaces

A `locked` status is set only by Trust & Safety or the Security team. Support agents must not
share the reason for a lock with the customer and must escalate the ticket to the
`trust-safety` queue instead of attempting to resolve it.

## Role-based access inside a workspace

- **Owner** — billing, plan changes, SSO settings, delete workspace.
- **Admin** — manage members, integrations, and workspace settings; cannot change billing.
- **Member** — create and edit projects and tasks.
- **Guest** — view and comment on invited projects only.

Only Owners can change the plan or update the payment method.
