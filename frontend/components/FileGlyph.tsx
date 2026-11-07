const LABELS: Record<string, string> = { pdf: "PDF", markdown: "MD", html: "HTML", text: "TXT" };

/** Small square tile with the document's format, used in source lists. */
export function FileGlyph({ type }: { type: string }) {
  return (
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-background font-mono text-micro font-semibold tracking-wide text-foreground/80">
      {LABELS[type] ?? type}
    </span>
  );
}
