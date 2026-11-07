"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerView } from "@/components/copilot/AnswerView";
import { CustomerPanel } from "@/components/copilot/CustomerPanel";
import { ProgressSteps } from "@/components/copilot/ProgressSteps";
import { Icon } from "@/components/icons";
import { Button, Card, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupText,
  InputGroupTextarea,
} from "@/components/ui/input-group";
import { Kbd } from "@/components/ui/kbd";
import { api, type ProgressEvent, type QueryResponse } from "@/lib/api";

const EXAMPLES: { tag: string; q: string }[] = [
  { tag: "Account", q: "Why can't the team create tasks or upload files?" },
  { tag: "Plans", q: "Is SSO available on our plan?" },
  { tag: "Billing", q: "Can we get a refund for an annual plan bought 20 days ago?" },
  { tag: "Errors", q: "What does error SSO-401 mean?" },
  { tag: "Integrations", q: "Why aren't GitHub pull requests linking to tasks?" },
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
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [startedAt, setStartedAt] = useState(0);
  const nextId = useRef(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const handledQuery = useRef(false);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => {
    if (turns.length || pending) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [turns, pending]);

  // Leaving the page (or switching user, which remounts it) stops the answer in flight.
  useEffect(() => () => inFlight.current?.abort(), []);

  const changeCustomer = (id: string | null) => {
    // A conversation is about one customer: switching starts a fresh one.
    setCustomerId(id);
    setConversationId(null);
    setTurns([]);
  };

  const ask = async (text: string) => {
    const q = text.trim();
    if (!q || pending) return;
    const controller = new AbortController();
    inFlight.current = controller;
    setQuestion("");
    setTurns((t) => [...t, { kind: "user", id: nextId.current++, text: q }]);
    setPending(true);
    setProgress([]);
    setStartedAt(Date.now());
    try {
      const response = await api.queryStream(
        { question: q, customer_id: customerId, conversation_id: conversationId },
        (event) => setProgress((p) => [...p, event]),
        controller.signal,
      );
      setConversationId(response.conversation_id);
      setTurns((t) => [...t, { kind: "assistant", id: nextId.current++, response }]);
    } catch (error) {
      if (controller.signal.aborted) return;
      setTurns((t) => [...t, { kind: "error", id: nextId.current++, error, question: q }]);
    } finally {
      if (inFlight.current === controller) inFlight.current = null;
      if (!controller.signal.aborted) setPending(false);
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
        compact
        title="Ask, check, then act."
        description="Cited answers from the docs, account facts from read-only tools, and ticket changes that wait for your approval."
        actions={
          turns.length > 0 && (
            <Button
              onClick={() => {
                setConversationId(null);
                setTurns([]);
              }}
              disabled={pending}
            >
              <Icon name="plus" className="size-3.5" />
              New conversation
            </Button>
          )
        }
      />
      <div className="grid gap-5 lg:grid-cols-[19rem_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-20 lg:self-start">
          <CustomerPanel customerId={customerId} onChange={changeCustomer} disabled={pending} />
        </div>

        <Card className="flex min-h-[36rem] flex-col overflow-hidden border">
          <div className="flex-1 space-y-7 px-5 py-6 sm:px-8" data-testid="chat-thread">
            {turns.length === 0 && !pending && (
              <div className="mx-auto max-w-2xl py-2">
                <p className="eyebrow">New conversation</p>
                <p className="mt-1.5 text-[20px] font-semibold tracking-[-0.02em] text-foreground">
                  Start with a question.
                </p>
                <p className="mt-1.5 text-body text-muted-foreground">
                  {customerId
                    ? "The copilot can now read this customer's account. Ask anything, or try one of these."
                    : "Pick a customer on the left to let the copilot read their account, or try one of these."}
                </p>
                <div className="mt-6 grid gap-2.5 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button
                      key={ex.q}
                      type="button"
                      disabled={pending}
                      onClick={() => ask(ex.q)}
                      className="group flex flex-col gap-1.5 rounded-lg border bg-card px-4 py-3 text-left shadow-card transition-colors outline-none hover:bg-accent focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 disabled:pointer-events-none disabled:opacity-50"
                    >
                      <span className="flex items-center justify-between gap-2" aria-hidden>
                        <span className="eyebrow group-hover:text-primary">{ex.tag}</span>
                        <Icon
                          name="arrowRight"
                          className="size-3.5 -translate-x-1 text-muted-foreground opacity-0 transition-[opacity,translate] group-hover:translate-x-0 group-hover:opacity-100"
                        />
                      </span>
                      <span className="text-body leading-snug text-foreground/85 group-hover:text-foreground">
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
                  <div className="max-w-[80%] rounded-lg rounded-br-sm bg-primary px-4 py-2.5 text-ui-lg leading-relaxed whitespace-pre-wrap text-primary-foreground shadow-card">
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
                      <Icon name="refresh" className="size-3.5" />
                      Retry
                    </Button>
                  </div>
                </div>
              ),
            )}
            {pending && (
              <div className="flex gap-3.5" data-testid="copilot-loading">
                <AssistantMark />
                <ProgressSteps events={progress} startedAt={startedAt} />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t bg-muted/40 px-4 py-4 sm:px-6">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void ask(question);
              }}
            >
              <InputGroup className="rounded-lg bg-card shadow-card has-disabled:bg-card has-disabled:opacity-100">
                <InputGroupTextarea
                  aria-label="Question"
                  data-testid="question-input"
                  className="max-h-48 min-h-11 px-3.5 pt-3 leading-relaxed placeholder:text-muted-foreground/70"
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
                <InputGroupAddon align="block-end" className="gap-1.5 px-3.5">
                  <InputGroupText className="hidden gap-1 text-caption font-normal text-muted-foreground/80 sm:flex">
                    <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> new line
                  </InputGroupText>
                  <InputGroupButton
                    type="submit"
                    variant="default"
                    size="icon-sm"
                    disabled={pending || !question.trim()}
                    aria-label="Ask"
                    className="ml-auto rounded-md"
                  >
                    {pending ? (
                      <Spinner className="size-3.5 border-primary-foreground/30 border-t-primary-foreground" />
                    ) : (
                      <Icon name="send" className="size-4" />
                    )}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
            </form>
            <p className="mt-2 px-1 text-caption text-muted-foreground/70">
              Answers cite their sources or abstain. Write actions always wait for a human.
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
      className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full border bg-card shadow-card"
      aria-hidden
    >
      <svg viewBox="0 0 32 32" className="size-4">
        <circle cx="13" cy="16" r="6.5" fill="none" stroke="var(--foreground)" strokeWidth="2.6" />
        <circle cx="21.5" cy="16" r="3.2" fill="var(--primary)" />
      </svg>
    </span>
  );
}
