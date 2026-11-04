"use client";

import { api, type Customer, type Ticket } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { Icon } from "../icons";
import { Card, cx, ErrorBanner, inputClass, Spinner, StatusBadge } from "../ui";

/** Customer picker + the selected customer's card and tickets. */
export function CustomerPanel({
  customerId,
  onChange,
}: {
  customerId: string | null;
  onChange: (id: string | null) => void;
}) {
  const customers = useAsync(() => api.customers(), []);
  const customer = customers.data?.find((c) => c.id === customerId) ?? null;

  return (
    <div className="space-y-3">
      <Card className="p-4">
        <label className="block">
          <span className="eyebrow">Customer context</span>
          <span className="relative mt-2 block">
            <select
              data-testid="customer-picker"
              className={cx(inputClass, "cursor-pointer appearance-none pr-8")}
              value={customerId ?? ""}
              onChange={(e) => onChange(e.target.value || null)}
              disabled={customers.loading && !customers.data}
            >
              <option value="">No customer (docs only)</option>
              {customers.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.external_id})
                </option>
              ))}
            </select>
            <Icon
              name="chevronDown"
              className="pointer-events-none absolute top-1/2 right-2.5 h-3.5 w-3.5 -translate-y-1/2 text-ink-3"
            />
          </span>
        </label>
        {customers.error != null && (
          <div className="mt-2">
            <ErrorBanner error={customers.error} />
          </div>
        )}
        {customer ? (
          <CustomerCard customer={customer} />
        ) : (
          <p className="mt-3 text-[12.5px] leading-relaxed text-ink-3">
            With a customer selected, the copilot can read their account through tools and propose
            ticket actions.
          </p>
        )}
      </Card>
      {customer && <TicketList customerId={customer.id} />}
    </div>
  );
}

function CustomerCard({ customer }: { customer: Customer }) {
  const initials = customer.name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("");
  return (
    <div className="mt-4 border-t border-line pt-4" data-testid="customer-card">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-paper-2 font-display text-[1.15rem] text-ink">
          {initials}
        </span>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-medium text-ink">{customer.name}</div>
          <div className="font-mono text-[11px] text-ink-3">{customer.external_id}</div>
        </div>
      </div>
      <dl className="mt-3.5 grid grid-cols-2 gap-2 text-[12px]">
        <div className="rounded-lg bg-paper px-2.5 py-2">
          <dt className="text-ink-3">Plan</dt>
          <dd className="mt-0.5 font-medium text-ink capitalize">{customer.plan}</dd>
        </div>
        <div className="rounded-lg bg-paper px-2.5 py-2">
          <dt className="text-ink-3">Account</dt>
          <dd className="mt-1">
            <StatusBadge status={customer.account_status} />
          </dd>
        </div>
      </dl>
    </div>
  );
}

function TicketList({ customerId }: { customerId: string }) {
  const tickets = useAsync<Ticket[]>(() => api.tickets(customerId), [customerId]);

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
        <h3 className="eyebrow">Tickets{tickets.data ? ` · ${tickets.data.length}` : ""}</h3>
        {tickets.loading && <Spinner className="h-3 w-3" />}
      </div>
      {tickets.error != null && (
        <div className="px-4 pb-3">
          <ErrorBanner error={tickets.error} />
        </div>
      )}
      {tickets.data?.length === 0 && (
        <p className="px-4 pb-4 text-[12.5px] text-ink-3">No tickets.</p>
      )}
      <ul className="divide-y divide-line border-t border-line">
        {tickets.data?.map((t) => (
          <li key={t.id}>
            <details className="group px-4 py-3 open:bg-paper/50">
              <summary className="cursor-pointer list-none">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[13px] leading-snug font-medium text-ink-2 group-open:text-ink">
                    {t.subject}
                  </span>
                  <StatusBadge status={t.status} />
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[11px] text-ink-3">
                  <span className="font-mono">{t.external_id}</span>
                  <span className="text-ink-4">·</span>
                  <span className={cx(["high", "urgent"].includes(t.priority) && "text-warn")}>
                    {t.priority}
                  </span>
                  <span className="text-ink-4">·</span>
                  <span>{formatDate(t.created_at)}</span>
                </div>
                {t.tags.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {t.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded border border-line px-1 font-mono text-[10.5px] text-ink-3"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
              </summary>
              <p className="mt-2.5 text-[12.5px] leading-relaxed whitespace-pre-wrap text-ink-2">
                {t.body}
              </p>
            </details>
          </li>
        ))}
      </ul>
    </Card>
  );
}
