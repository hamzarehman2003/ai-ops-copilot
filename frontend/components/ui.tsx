"use client";

import { useEffect, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";
import { errorMessage, ApiError } from "@/lib/api";
import { Icon } from "./icons";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

// ---------- Buttons ----------

type Variant = "primary" | "secondary" | "danger" | "ghost" | "success";

const variants: Record<Variant, string> = {
  primary:
    "bg-ink text-paper border-ink hover:bg-ink-2 hover:border-ink-2 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]",
  secondary: "bg-surface text-ink border-line-strong hover:border-ink-4 hover:bg-paper",
  danger: "bg-surface text-bad border-line-strong hover:border-bad/40 hover:bg-bad-soft",
  success: "bg-ok text-white border-ok hover:brightness-110",
  ghost: "bg-transparent text-ink-2 border-transparent hover:bg-paper-2 hover:text-ink",
};

export function Button({
  variant = "secondary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg border font-medium whitespace-nowrap",
        "transition-[background-color,border-color,color,filter] duration-150",
        "disabled:pointer-events-none disabled:opacity-45",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        size === "sm" ? "h-7 px-2.5 text-[12.5px]" : "h-9 px-3.5 text-[13.5px]",
        variants[variant],
        className,
      )}
    />
  );
}

// ---------- Badges ----------

export type Tone = "gray" | "green" | "amber" | "red" | "blue" | "indigo" | "purple";

const tones: Record<Tone, string> = {
  gray: "bg-paper-2 text-ink-2",
  green: "bg-ok-soft text-ok",
  amber: "bg-warn-soft text-warn",
  red: "bg-bad-soft text-bad",
  blue: "bg-info-soft text-info",
  indigo: "bg-accent-soft text-accent-ink",
  purple: "bg-plum-soft text-plum",
};

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
    <span
      title={title}
      className={cx(
        "inline-flex h-5 items-center gap-1 rounded-md px-1.5 text-[11.5px] leading-none font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
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

/** Status pill: a coloured dot plus the label, so state is never colour alone. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const pulse = status === "processing" || status === "pending";
  return (
    <Badge tone={STATUS_TONES[status] ?? "gray"} className={className}>
      <span className={cx("h-1.5 w-1.5 rounded-full bg-current", pulse && "animate-pulse")} />
      {status.replace(/_/g, " ")}
    </Badge>
  );
}

// ---------- Layout bits ----------

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      {...props}
      className={cx("rounded-xl border border-line bg-surface shadow-card", className)}
    />
  );
}

/** Card with a titled header row. */
export function Panel({
  title,
  eyebrow,
  actions,
  children,
  className,
  bodyClassName,
  ...props
}: Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <Card {...props} className={cx("flex flex-col", className)}>
      <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0">
          {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
          <h2 className="text-[14px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      <div className={cx("flex-1 px-5 pb-5", bodyClassName)}>{children}</div>
    </Card>
  );
}

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="max-w-2xl min-w-0">
        {eyebrow && <div className="eyebrow mb-2.5">{eyebrow}</div>}
        <h1 className="font-display text-[2.35rem] leading-[1.05] tracking-[-0.015em] text-ink sm:text-[2.6rem]">
          {title}
        </h1>
        {description && (
          <p className="mt-2.5 text-[14.5px] leading-relaxed text-ink-3">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** One headline number with a label and an optional footnote. */
export function StatTile({
  label,
  value,
  unit,
  note,
  accent,
  loading,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  note?: ReactNode;
  accent?: boolean;
  loading?: boolean;
}) {
  return (
    <Card {...props} className={cx("relative overflow-hidden px-5 py-4", props.className)}>
      {accent && <span className="absolute inset-y-0 left-0 w-[3px] bg-accent" aria-hidden />}
      <div className="eyebrow">{label}</div>
      <div className="mt-3 flex items-baseline gap-1.5">
        {loading ? (
          <span className="h-9 w-20 animate-pulse rounded-md bg-paper-2" />
        ) : (
          <span className="font-display text-[2.6rem] leading-none tracking-[-0.02em] text-ink tabular-nums">
            {value}
          </span>
        )}
        {unit && !loading && <span className="text-[13px] text-ink-3">{unit}</span>}
      </div>
      {note && <div className="mt-2.5 text-[12.5px] leading-snug text-ink-3">{note}</div>}
    </Card>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        "inline-block h-4 w-4 animate-spin rounded-full border-[1.5px] border-line-strong border-t-ink",
        className,
      )}
    />
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 px-1 py-8 text-[13px] text-ink-3">
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
            : "Error";
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 rounded-lg border border-bad/20 bg-bad-soft px-3.5 py-2.5 text-[13px] text-bad"
    >
      <div className="flex gap-2">
        <Icon name="alert" className="mt-px h-4 w-4 shrink-0" />
        <div>
          <span className="font-semibold">
            {label}
            {status ? ` (${status})` : ""}
          </span>{" "}
          <span className="text-bad/90">{errorMessage(error)}</span>
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="rounded p-0.5 text-bad/70 hover:bg-bad/10 hover:text-bad"
          aria-label="Dismiss"
        >
          <Icon name="close" className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-strong bg-surface/60 px-6 py-12 text-center">
      <p className="font-display text-[1.45rem] leading-tight text-ink">{title}</p>
      {children && (
        <div className="mx-auto mt-2 max-w-md text-[13.5px] leading-relaxed text-ink-3">
          {children}
        </div>
      )}
    </div>
  );
}

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cx(
        "max-h-80 overflow-auto rounded-lg bg-[#1d1c1a] p-3.5 font-mono text-[11.5px] leading-relaxed text-[#e9e6de]",
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
      <div className="h-1 w-16 overflow-hidden rounded-full bg-paper-2">
        <div
          className={cx("h-full rounded-full", pct >= 60 ? "bg-ink" : "bg-ink-4")}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-[11px] text-ink-3 tabular-nums">{Math.round(pct)}%</span>
    </div>
  );
}

// ---------- Drawer ----------

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
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]" onClick={onClose} />
      <div
        className={cx(
          "relative flex h-full w-full animate-rise flex-col border-l border-line bg-paper shadow-pop",
          wide ? "max-w-5xl" : "max-w-2xl",
        )}
      >
        <div className="flex items-center justify-between gap-4 border-b border-line bg-surface px-6 py-4">
          <h2 className="min-w-0 truncate font-display text-[1.6rem] leading-tight text-ink">
            {title}
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            <Icon name="close" className="h-3.5 w-3.5" />
            Close
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">{children}</div>
      </div>
    </div>
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
    <div className="mb-5 flex gap-5 border-b border-line" role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="tab"
          aria-selected={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "-mb-px border-b-[1.5px] pt-1 pb-2.5 text-[13.5px] font-medium transition-colors",
            value === o.value
              ? "border-ink text-ink"
              : "border-transparent text-ink-3 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
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
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex flex-wrap gap-0.5 rounded-lg border border-line bg-paper-2 p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "h-8 rounded-md px-3 text-[12.5px] font-medium transition-all",
            value === o.value
              ? "bg-surface text-ink shadow-card ring-1 ring-line"
              : "text-ink-3 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const inputClass =
  "w-full rounded-lg border border-line-strong bg-surface px-3 py-2 text-[13.5px] text-ink placeholder:text-ink-4 transition-[border-color,box-shadow] focus:border-ink-3 focus:ring-[3px] focus:ring-ink/[0.07] focus:outline-none disabled:bg-paper disabled:text-ink-3";

export const labelClass = "block text-[12px] font-medium text-ink-2";
