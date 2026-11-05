"use client";

/*
 * App-level building blocks on top of the shadcn/ui primitives in components/ui/.
 * Pages use these (PageHeader, Panel, StatTile, StatusBadge...) so the look stays consistent;
 * for anything else they use the shadcn components directly.
 */

import type { ComponentProps, HTMLAttributes, ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge as ShadBadge } from "@/components/ui/badge";
import { Button as ShadButton } from "@/components/ui/button";
import {
  Card as ShadCard,
  CardAction,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs as ShadTabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { ApiError, errorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Icon, type IconName } from "./icons";

export { Skeleton };

/** Kept for existing call sites; same as `cn` without tailwind-merge. */
export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

// ---------- Buttons ----------

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success";

const VARIANTS = {
  primary: "default",
  secondary: "outline",
  danger: "destructive",
  ghost: "ghost",
  success: "default",
} as const;

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: Omit<ComponentProps<typeof ShadButton>, "variant" | "size"> & {
  variant?: Variant;
  size?: "sm" | "md";
}) {
  return (
    <ShadButton
      type="button"
      {...props}
      variant={VARIANTS[variant]}
      size={size === "sm" ? "default" : "lg"}
      className={cn(
        size === "md" && "px-3.5",
        variant === "primary" && "shadow-[inset_0_1px_0_rgb(255_255_255/0.14)]",
        variant === "secondary" && "bg-card shadow-card",
        variant === "success" && "bg-success text-white hover:bg-success/90",
        className,
      )}
    />
  );
}

// ---------- Badges and status stamps ----------

export type Tone = "gray" | "green" | "amber" | "red" | "blue" | "indigo" | "purple";

const TONES: Record<Tone, string> = {
  gray: "border-border bg-muted text-muted-foreground",
  green: "border-success/30 bg-success/10 text-success",
  amber: "border-warning/35 bg-warning/10 text-warning",
  red: "border-destructive/30 bg-destructive/8 text-destructive",
  blue: "border-info/30 bg-info/10 text-info",
  indigo: "border-primary/25 bg-primary/8 text-primary",
  purple: "border-plum/30 bg-plum/10 text-plum",
};

/** Quiet metadata chip: "312 tokens", "p. 2", "v3". */
export function Badge({
  tone = "gray",
  children,
  className,
  title,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <ShadBadge
      variant="outline"
      title={title}
      className={cn("rounded-sm font-mono font-normal", TONES[tone], className)}
    >
      {children}
    </ShadBadge>
  );
}

const STATUS_TONES: Record<string, Tone> = {
  // ingestion
  ready: "green",
  pending: "amber",
  processing: "blue",
  failed: "red",
  // account
  active: "green",
  past_due: "amber",
  suspended: "red",
  locked: "red",
  trialing: "blue",
  // actions
  approved: "blue",
  executed: "green",
  rejected: "gray",
  // tool calls
  ok: "green",
  denied: "amber",
  error: "red",
  timeout: "purple",
  // tickets
  open: "blue",
  solved: "green",
  closed: "gray",
  // priority
  low: "gray",
  normal: "gray",
  high: "amber",
  urgent: "red",
};

/** Small-caps status stamp: READY, PENDING, SUSPENDED. Text plus colour, never colour alone. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const pulse = status === "processing" || status === "pending";
  return (
    <ShadBadge
      variant="outline"
      className={cn(
        "h-[22px] gap-1.5 rounded-sm px-2 text-[10.5px] tracking-[0.08em] uppercase",
        TONES[STATUS_TONES[status] ?? "gray"],
        className,
      )}
    >
      {pulse && (
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-50" />
          <span className="relative inline-flex size-1.5 rounded-full bg-current" />
        </span>
      )}
      {status.replace(/_/g, " ")}
    </ShadBadge>
  );
}

// ---------- Cards ----------

/** A shadcn Card without its built-in padding, for containers that lay out their own content. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <ShadCard {...props} className={cn("gap-0 py-0 shadow-card ring-0", className)} />;
}

/** Card with a header (eyebrow + title, optional actions) and an optional muted footer. */
export function Panel({
  title,
  eyebrow,
  actions,
  footer,
  children,
  className,
  bodyClassName,
  ...props
}: Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <ShadCard {...props} className={cn("shadow-card ring-0", className)}>
      <CardHeader>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <CardTitle className="text-[16px] font-semibold tracking-[-0.01em]">{title}</CardTitle>
        {actions && <CardAction className="flex items-center gap-2">{actions}</CardAction>}
      </CardHeader>
      <CardContent className={cn("flex-1", bodyClassName)}>{children}</CardContent>
      {footer && (
        <CardFooter className="gap-2 border-t bg-muted/40 py-3 text-[13px] text-muted-foreground">
          {footer}
        </CardFooter>
      )}
    </ShadCard>
  );
}

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  compact,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** One line: smaller title with the description beside it (pages where content should start high). */
  compact?: boolean;
}) {
  if (compact) {
    return (
      <header className="mb-5 flex flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-[1.375rem] leading-tight font-semibold tracking-[-0.02em]">{title}</h1>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </header>
    );
  }
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b pb-6">
      <div className="max-w-2xl min-w-0">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="mt-2 text-[1.875rem] leading-tight font-semibold tracking-[-0.025em]">
          {title}
        </h1>
        {description && (
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

const VALUE_TONES = {
  default: "text-foreground",
  success: "text-success",
  warning: "text-warning",
  danger: "text-destructive",
  accent: "text-primary",
};

/** A key number: small-caps label, a big figure, one quiet line underneath. */
export function StatTile({
  label,
  value,
  unit,
  note,
  tone = "default",
  loading,
  className,
  ...props
}: Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  note?: ReactNode;
  tone?: keyof typeof VALUE_TONES;
  loading?: boolean;
}) {
  return (
    <Card {...props} className={cn("p-5", className)}>
      <p className="eyebrow">{label}</p>
      <div className="mt-3 flex items-baseline gap-1.5">
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <span
            className={cn(
              "numeric text-[2rem] leading-none font-medium tracking-[-0.03em]",
              VALUE_TONES[tone],
            )}
          >
            {value}
          </span>
        )}
        {unit && !loading && <span className="text-[13px] text-muted-foreground">{unit}</span>}
      </div>
      {note && <div className="mt-2.5 text-[13px] leading-snug text-muted-foreground">{note}</div>}
    </Card>
  );
}

// ---------- Feedback ----------

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block size-4 animate-spin rounded-full border-[1.5px] border-input border-t-primary",
        className,
      )}
    />
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 px-1 py-8 text-[13px] text-muted-foreground">
      <Spinner /> {label}
    </div>
  );
}

export function ErrorBanner({ error, onDismiss }: { error: unknown; onDismiss?: () => void }) {
  if (!error) return null;
  const status = error instanceof ApiError ? error.status : null;
  const label =
    status === 403
      ? "Not allowed"
      : status === 404
        ? "Not found"
        : status === 409
          ? "Conflict"
          : status === 422
            ? "Invalid input"
            : "Something went wrong";
  return (
    <Alert variant="destructive" className="relative border-destructive/30 bg-destructive/5">
      <Icon name="alert" />
      <AlertTitle>
        {label}
        {status ? ` (${status})` : ""}
      </AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="absolute top-2.5 right-2.5 rounded p-0.5 opacity-70 hover:opacity-100"
          aria-label="Dismiss"
        >
          <Icon name="close" className="size-3.5" />
        </button>
      )}
    </Alert>
  );
}

/** Nothing here yet: a line icon, one title, one line of help, one optional action. */
export function EmptyState({
  title,
  icon = "inbox",
  action,
  children,
  compact,
}: {
  title: string;
  icon?: IconName;
  action?: ReactNode;
  children?: ReactNode;
  /** Less padding, for use inside a card. */
  compact?: boolean;
}) {
  return (
    <Empty className={cn("border border-dashed", compact ? "py-8" : "py-14")}>
      <EmptyHeader>
        <EmptyMedia variant="icon" className="rounded-full border bg-card shadow-card">
          <Icon name={icon} strokeWidth={1.5} />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {children && <EmptyDescription>{children}</EmptyDescription>}
      </EmptyHeader>
      {action && <EmptyContent>{action}</EmptyContent>}
    </Empty>
  );
}

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto rounded-lg bg-code p-3.5 font-mono text-[11.5px] leading-relaxed text-code-foreground",
        className,
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/** Horizontal 0..1 bar (citation relevance). */
export function MeterBar({ value, label }: { value: number; label?: string }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="flex items-center gap-2" title={label}>
      <div className="h-1 w-16 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full", pct >= 60 ? "bg-primary" : "bg-primary/40")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="numeric text-[11px] text-muted-foreground">{Math.round(pct)}%</span>
    </div>
  );
}

// ---------- Drawer (shadcn Sheet) ----------

export function Drawer({
  open,
  onClose,
  title,
  children,
  wide,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className={cn("w-full gap-0 bg-background p-0", wide ? "sm:max-w-5xl" : "sm:max-w-2xl")}
      >
        <SheetHeader className="border-b bg-card px-6 py-4">
          <SheetTitle className="truncate pr-8 text-[17px] font-semibold tracking-[-0.01em]">
            {title}
          </SheetTitle>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </SheetContent>
    </Sheet>
  );
}

// ---------- Tabs / segmented control ----------

export function Tabs<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
}) {
  return (
    <ShadTabs value={value} onValueChange={(v) => onChange(v as T)} className="mb-5">
      <TabsList variant="line" className="h-10 w-full justify-start gap-4 rounded-none border-b p-0">
        {options.map((o) => (
          <TabsTrigger
            key={o.value}
            value={o.value}
            className="flex-none px-0.5 text-[14px] after:bottom-[-1px]!"
          >
            {o.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </ShadTabs>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
  label: string;
}) {
  return (
    <ToggleGroup
      type="single"
      variant="outline"
      aria-label={label}
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      className="bg-card shadow-card"
    >
      {options.map((o) => (
        <ToggleGroupItem
          key={o.value}
          value={o.value}
          className="h-8 px-3 text-[13px] data-[state=on]:bg-primary/10 data-[state=on]:text-primary"
        >
          {o.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

// ---------- Forms ----------

/** Classes matching the shadcn Input, for native elements we style ourselves. */
export const inputClass =
  "w-full min-w-0 rounded-md border border-input bg-card px-3 py-2 text-sm shadow-card transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:opacity-50";

export const labelClass = "block text-[13px] font-medium text-foreground/80";
