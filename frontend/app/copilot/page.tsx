"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/copilot/AnswerView";
import { CustomerPanel } from "@/components/copilot/CustomerPanel";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import { api, type QueryResponse } from "@/lib/api";

const EXAMPLES: { tag: string; q: string }[] = [
  { tag: "Account", q: "Why can't the team create tasks or upload files?" },
  { tag: "Plans", q: "Is SSO available on our plan?" },
  { tag: "Billing", q: "Can we get a refund for an annual plan bought 20 days ago?" },
  { tag: "Errors", q: "What does error SSO-401 mean?" },
  { tag: "Off-topic · abstains", q: "What is the capital of France?" },
];

type Turn =
  | { kind: "user"; id: number; text: string }
  | { kind: "assistant"; id: number; response: QueryResponse }
  | { kind: "error"; id: number; error: unknown; question: string };

export default function CopilotPage() {
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const handledQuery = useRef(false);

  useEffect(() => {
    if (turns.length || pending) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [turns, pending]);

  const changeCustomer = (id: string | null) => {
    // A conversation is about one customer: switching starts a fresh one.
    setCustomerId(id);
    setConversationId(null);
    setTurns([]);
  };

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || pending) return;
    setQuestion("");
    setTurns((t) => [...t, { kind: "user", id: nextId.current++, text: q }]);
    setPending(true);
    try {
      const response = await api.query({
        question: q,
        customer_id: customerId,
        conversation_id: conversationId,
      });
      setConversationId(response.conversation_id);
      setTurns((t) => [...t, { kind: "assistant", id: nextId.current++, response }]);
    } catch (error) {
      setTurns((t) => [...t, { kind: "error", id: nextId.current++, error, question: q }]);
    } finally {
      setPending(false);
    }
  };

  // A question handed over from the Overview ask bar (/copilot?q=...).
  useEffect(() => {
    if (handledQuery.current) return;
    handledQuery.current = true;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/copilot");
      void ask(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="animate-rise">
      <PageHeader
        eyebrow="Copilot"
        title="Ask, check, then act."
        description="Answers grounded in the docs with citations, account facts from read-only tools, and ticket changes that wait for your approval."
        actions={
          turns.length > 0 && (
            <Button
              onClick={() => {
                setConversationId(null);
                setTurns([]);
              }}
              disabled={pending}
            >
              <Icon name="plus" className="h-3.5 w-3.5" />
              New conversation
            </Button>
          )
        }
      />
      <div className="grid gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <CustomerPanel customerId={customerId} onChange={changeCustomer} />
        </div>

        <Card className="flex min-h-[36rem] flex-col overflow-hidden">
          <div className="flex-1 space-y-7 px-5 py-6 sm:px-8" data-testid="chat-thread">
            {turns.length === 0 && !pending && (
              <div className="mx-auto max-w-2xl py-6">
                <p className="font-display text-[1.75rem] leading-tight text-ink">
                  Start with a question.
                </p>
                <p className="mt-1.5 text-[13.5px] text-ink-3">
                  Pick a customer on the left to let the copilot read their account, or try one of
                  these.
                </p>
                <div className="mt-6 grid gap-2.5 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.q}
                      type="button"
                      disabled={pending}
                      onClick={() => ask(ex.q)}
                      className="group rounded-xl border border-line bg-paper/50 px-4 py-3 text-left transition-[border-color,background-color] hover:border-line-strong hover:bg-surface disabled:opacity-50"
                    >
                      <span className="eyebrow block text-ink-4 group-hover:text-accent" aria-hidden>
                        {ex.tag}
                      </span>
                      <span className="mt-1 block text-[13.5px] leading-snug text-ink-2 group-hover:text-ink">
                        {ex.q}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((turn) =>
              turn.kind === "user" ? (
                <div key={turn.id} className="flex animate-rise justify-end">
                  <div className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap text-paper">
                    {turn.text}
                  </div>
                </div>
              ) : turn.kind === "assistant" ? (
                <div key={turn.id} className="flex animate-rise gap-3.5">
                  <AssistantMark />
                  <div className="min-w-0 flex-1">
                    <AnswerView response={turn.response} />
                  </div>
                </div>
              ) : (
                <div key={turn.id} className="flex gap-3.5">
                  <AssistantMark />
                  <div className="flex-1 space-y-2">
                    <ErrorBanner error={turn.error} />
                    <Button size="sm" onClick={() => ask(turn.question)} disabled={pending}>
                      <Icon name="refresh" className="h-3.5 w-3.5" />
                      Retry
                    </Button>
                  </div>
                </div>
              ),
            )}
            {pending && (
              <div className="flex gap-3.5" data-testid="copilot-loading">
                <AssistantMark />
                <div className="flex items-center gap-2.5 pt-1 text-[13px] text-ink-3">
                  <Spinner className="h-3.5 w-3.5" />
                  Retrieving sources and drafting an answer…
                  <span className="hidden text-ink-4 sm:inline">
                    the first query can take ~20 s while models load
                  </span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-line bg-paper/40 px-4 py-4 sm:px-6">
            <form
              className="flex items-end gap-2 rounded-xl border border-line-strong bg-surface p-1.5 pl-3.5 transition-[border-color,box-shadow] focus-within:border-ink-3 focus-within:ring-[3px] focus-within:ring-ink/[0.06]"
              onSubmit={(e) => {
                e.preventDefault();
                void ask(question);
              }}
            >
              <textarea
                aria-label="Question"
                data-testid="question-input"
                className="max-h-48 min-h-[2.25rem] flex-1 resize-none bg-transparent py-2 text-[14px] leading-relaxed text-ink placeholder:text-ink-4 focus:outline-none"
                rows={1}
                maxLength={2000}
                placeholder="Ask about this customer, a policy, an error code…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void ask(question);
                  }
                }}
              />
              <Button
                type="submit"
                variant="primary"
                disabled={pending || !question.trim()}
                aria-label="Ask"
                className="h-9 w-9 shrink-0 px-0! disabled:border-line disabled:bg-paper-2 disabled:text-ink-4 disabled:opacity-100"
              >
                {pending ? (
                  <Spinner className="h-3.5 w-3.5 border-paper/30 border-t-paper" />
                ) : (
                  <Icon name="send" className="h-4 w-4" />
                )}
              </Button>
            </form>
            <p className="mt-2 px-1 text-[11.5px] text-ink-4">
              Enter to send · Shift + Enter for a new line · answers cite their sources or abstain
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}

function AssistantMark() {
  return (
    <span
      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line bg-paper"
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="h-4 w-4">
        <circle cx="13" cy="16" r="6.5" fill="none" stroke="var(--color-ink)" strokeWidth="2.6" />
        <circle cx="21.5" cy="16" r="3.2" fill="var(--color-accent)" />
      </svg>
    </span>
  );
}
