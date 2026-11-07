"use client";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import { api, type Customer, type Ticket } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { cn } from "@/lib/utils";
import { Icon } from "../icons";
import { Badge, Card, ErrorBanner, Spinner, StatusBadge } from "../ui";

/** Customer picker + the selected customer's card and tickets. */
export function CustomerPanel({
  customerId,
  onChange,
  disabled = false,
}: {
  customerId: string | null;
  onChange: (id: string | null) => void;
  /** While an answer is in flight: switching customer mid-answer would mix conversations. */
  disabled?: boolean;
}) {
  const customers = useAsync(() => api.customers(), []);
  const customer = customers.data?.find((c) => c.id === customerId) ?? null;

  return (
    <div className="space-y-3">
      <Card className="border p-4">
        <Label htmlFor="customer-picker" className="eyebrow text-[0.6875rem] leading-normal">
          Customer context
        </Label>
        <NativeSelect
          id="customer-picker"
          data-testid="customer-picker"
          className="mt-2 w-full"
          value={customerId ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
          disabled={disabled || (customers.loading && !customers.data)}
        >
          <NativeSelectOption value="">No customer (docs only)</NativeSelectOption>
          {customers.data?.map((c) => (
            <NativeSelectOption key={c.id} value={c.id}>
              {c.name} ({c.external_id})
            </NativeSelectOption>
          ))}
        </NativeSelect>
        {customers.error != null && (
          <div className="mt-2">
            <ErrorBanner error={customers.error} />
          </div>
        )}
        {customer ? (
          <CustomerCard customer={customer} />
        ) : (
          <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">
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
    <div data-testid="customer-card">
      <Separator className="my-4" />
      <div className="flex items-center gap-3">
        <Avatar size="lg" className="rounded-md after:rounded-md">
          <AvatarFallback className="rounded-md bg-primary/10 text-[13px] font-semibold text-primary">
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <div className="truncate text-[14px] font-medium text-foreground">{customer.name}</div>
          <div className="font-mono text-[11px] text-muted-foreground">{customer.external_id}</div>
        </div>
      </div>
      <dl className="mt-3.5 grid grid-cols-2 gap-2 text-[12px]">
        <div className="rounded-md border bg-muted/40 px-2.5 py-2">
          <dt className="eyebrow">Plan</dt>
          <dd className="mt-1 font-medium text-foreground capitalize">{customer.plan}</dd>
        </div>
        <div className="rounded-md border bg-muted/40 px-2.5 py-2">
          <dt className="eyebrow">Account</dt>
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
    <Card className="overflow-hidden border">
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5">
        <h3 className="eyebrow">
          Tickets
          {tickets.data && <span className="numeric"> · {tickets.data.length}</span>}
        </h3>
        {tickets.loading && <Spinner className="size-3" />}
      </div>
      {tickets.error != null && (
        <div className="px-4 pb-3">
          <ErrorBanner error={tickets.error} />
        </div>
      )}
      {tickets.data?.length === 0 && (
        <p className="px-4 pb-4 text-[12.5px] text-muted-foreground">No tickets.</p>
      )}
      {!!tickets.data?.length && (
        <ul className="divide-y border-t">
          {tickets.data.map((t) => (
            <li key={t.id}>
              <details className="group px-4 py-3 open:bg-muted/40">
                <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
                  <div className="flex items-start justify-between gap-2">
                    <span className="flex min-w-0 items-start gap-1.5">
                      <Icon
                        name="chevronRight"
                        className="mt-0.5 size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
                      />
                      <span className="text-[13px] leading-snug font-medium text-foreground/85 group-open:text-foreground">
                        {t.subject}
                      </span>
                    </span>
                    <StatusBadge status={t.status} />
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 pl-5 text-[11px] text-muted-foreground">
                    <span className="font-mono">{t.external_id}</span>
                    <span className="text-muted-foreground/50">·</span>
                    <span
                      className={cn(["high", "urgent"].includes(t.priority) && "text-warning")}
                    >
                      {t.priority}
                    </span>
                    <span className="text-muted-foreground/50">·</span>
                    <span>{formatDate(t.created_at)}</span>
                  </div>
                  {t.tags.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1 pl-5">
                      {t.tags.map((tag) => (
                        <Badge key={tag} className="h-[18px] px-1 text-[10.5px]">
                          #{tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </summary>
                <p className="mt-2.5 pl-5 text-[12.5px] leading-relaxed whitespace-pre-wrap text-foreground/80">
                  {t.body}
                </p>
              </details>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
