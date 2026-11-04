import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApprovalCard } from "../components/ApprovalCard";
import { askAgent, errorMessage } from "../lib/api";
import { statusOf } from "../lib/http";
import type { AgentAction, AgentStep, ChatMessage } from "../types";
import "../styles/assistant.css";

interface Entry {
  role: "user" | "assistant";
  content: string;
  steps?: AgentStep[];
  actions?: AgentAction[];
}

const SUGGESTIONS = [
  "What needs fixing in my ledger?",
  "Invoice Acme for the logo, due in 7 days",
  "Which agreements haven't been accepted yet?",
];

const HISTORY_LIMIT = 20;

export function AssistantPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [entries, busy]);

  const send = async (text: string) => {
    const content = text.trim();
    if (!content || busy) return;
    const next: Entry[] = [...entries, { role: "user", content }];
    setEntries(next);
    setDraft("");
    setBusy(true);
    setProblem(null);
    try {
      const history: ChatMessage[] = next
        .map(({ role, content }) => ({ role, content: content.slice(0, 4000) }))
        .slice(-HISTORY_LIMIT);
      const reply = await askAgent(history);
      setEntries([...next, { role: "assistant", content: reply.reply, steps: reply.steps, actions: reply.actions }]);
    } catch (failure) {
      setEntries(entries);
      setDraft(content);
      setProblem(
        statusOf(failure) === 429
          ? "That's a lot of questions in a minute. Wait a moment, then ask again."
          : errorMessage(failure, "The assistant couldn't answer just now. Try again in a moment."),
      );
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(draft);
  };

  return (
    <div className="assistant">
      <header className="page-head">
        <div>
          <h1>Assistant</h1>
          <p>
            Ask about your agreements, invoices and proof. It prepares actions for you to approve,
            and never acts on its own.
          </p>
        </div>
      </header>

      <div className="chat" aria-live="polite">
        {entries.length === 0 && (
          <div className="chat-empty">
            <p className="muted">Try one of these:</p>
            <div className="row">
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" className="button button-quiet" onClick={() => send(suggestion)}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
        {entries.map((entry, index) => (
          <article key={index} className={`bubble bubble-${entry.role}`} aria-label={entry.role === "user" ? "You" : "Assistant"}>
            {entry.steps && entry.steps.length > 0 && (
              <ul className="steps" aria-label="What the assistant checked">
                {entry.steps.map((step, stepIndex) => (
                  <li key={stepIndex} data-ok={step.ok}>
                    {step.label}
                    {!step.ok && " (didn't work)"}
                  </li>
                ))}
              </ul>
            )}
            <p className="bubble-text">{entry.content}</p>
            {entry.actions?.map((action) => <ApprovalCard key={action.id} action={action} />)}
          </article>
        ))}
        {busy && (
          <p className="muted thinking" role="status">
            Checking your records…
          </p>
        )}
        <div ref={end} />
      </div>

      {problem && (
        <p className="alert" role="alert">
          {problem}
        </p>
      )}
      <form className="composer" onSubmit={submit}>
        <label htmlFor="ask" className="visually-hidden">
          Ask the assistant
        </label>
        <textarea
          id="ask"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }}
          placeholder="Ask about a client, an invoice or what to fix"
          rows={2}
          maxLength={4000}
        />
        <button type="submit" className="button" disabled={busy || !draft.trim()}>
          Ask
        </button>
      </form>
    </div>
  );
}
