"use client";

import type { ReactNode } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, type MessageTrace } from "@/lib/api";
import { formatMs, formatScore } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { cn } from "@/lib/utils";
import { Icon } from "../icons";
import { Card, Drawer, ErrorBanner, JsonView, Loading } from "../ui";
import { ToolCallList } from "./ToolCallList";

/** Retrieval trace for one answer: every candidate with its dense/lexical/RRF/rerank scores. */
export function TraceDrawer({
  messageId,
  open,
  onClose,
}: {
  messageId: string;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer open={open} onClose={onClose} title="Retrieval trace" wide>
      {open && <TraceBody messageId={messageId} />}
    </Drawer>
  );
}

const head = "eyebrow h-9 px-3 text-caption text-muted-foreground";
const num = "numeric px-3 text-right";

function TraceBody({ messageId }: { messageId: string }) {
  const { data, error, loading } = useAsync<MessageTrace>(() => api.trace(messageId), [messageId]);
  if (loading) return <Loading />;
  if (error) return <ErrorBanner error={error} />;
  if (!data) return null;
  const r = data.retrieval;

  return (
    <div className="space-y-6">
      {!r ? (
        <p className="text-ui text-muted-foreground">
          No retrieval trace was recorded for this message.
        </p>
      ) : (
        <>
          <div>
            <div className="eyebrow">Query</div>
            <p className="mt-1.5 text-[17px] leading-snug font-medium text-foreground">
              &ldquo;{r.query}&rdquo;
            </p>
            <div className="mt-4 grid grid-cols-3 gap-2.5 sm:max-w-md">
              <Fact label="Candidates" value={r.results.length} />
              <Fact label="Selected" value={r.results.filter((c) => c.selected).length} />
              <Fact label="Latency" value={formatMs(r.latency_ms)} />
            </div>
          </div>
          <Card className="overflow-hidden border">
            <Table className="text-meta" data-testid="trace-table">
              <TableHeader className="bg-muted/40">
                <TableRow className="hover:bg-transparent">
                  <TableHead className={head}>#</TableHead>
                  <TableHead className={head}>File</TableHead>
                  <TableHead className={head}>Heading</TableHead>
                  <TableHead className={cn(head, "text-right")}>Dense</TableHead>
                  <TableHead className={cn(head, "text-right")}>Lexical</TableHead>
                  <TableHead className={cn(head, "text-right")}>RRF</TableHead>
                  <TableHead className={cn(head, "text-right")}>Rerank</TableHead>
                  <TableHead className={head}>Selected</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.results.map((c, i) => (
                  <TableRow
                    key={c.chunk_id}
                    data-state={c.selected ? "selected" : undefined}
                    className={cn(
                      c.selected
                        ? "data-[state=selected]:bg-success/5"
                        : "text-muted-foreground",
                    )}
                  >
                    <TableCell className="numeric px-3 text-muted-foreground/70">{i + 1}</TableCell>
                    <TableCell className="px-3 font-mono text-foreground/85">{c.filename}</TableCell>
                    <TableCell
                      className="max-w-xs truncate px-3 text-foreground/85"
                      title={c.heading}
                    >
                      {c.heading}
                    </TableCell>
                    <TableCell className={num}>{c.dense_rank ?? "—"}</TableCell>
                    <TableCell className={num}>{c.lexical_rank ?? "—"}</TableCell>
                    <TableCell className={num}>{formatScore(c.rrf_score, 4)}</TableCell>
                    <TableCell className={cn(num, "font-medium text-foreground")}>
                      {formatScore(c.rerank_score)}
                    </TableCell>
                    <TableCell className="px-3">
                      {c.selected ? (
                        <span className="inline-flex items-center gap-1.5 font-medium text-success">
                          <span className="size-1.5 rounded-full bg-success" />
                          selected
                        </span>
                      ) : (
                        ""
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <Disclosure label="Retrieval params">
            <JsonView value={r.params} />
          </Disclosure>
        </>
      )}
      {data.tool_calls.length > 0 && <ToolCallList calls={data.tool_calls} />}
      <Disclosure label="Stored message data">
        <JsonView value={data.message.data} />
      </Disclosure>
    </div>
  );
}

function Disclosure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Collapsible className="group/disclosure">
      <CollapsibleTrigger className="inline-flex cursor-pointer items-center gap-1.5 rounded-sm text-small font-medium text-foreground/80 outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/30">
        <Icon
          name="chevronRight"
          className="size-3.5 text-muted-foreground transition-transform group-data-[state=open]/disclosure:rotate-90"
        />
        {label}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">{children}</CollapsibleContent>
    </Collapsible>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2 shadow-card">
      <div className="eyebrow">{label}</div>
      <div className="numeric mt-0.5 text-[15px] font-medium text-foreground">{value}</div>
    </div>
  );
}
