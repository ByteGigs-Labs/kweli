import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { createAgreement, errorMessage, readThread } from "../../lib/api";
import { statusOf } from "../../lib/http";
import type { EngagementDraft } from "../../types";

const CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD"];

interface Form {
  clientName: string;
  clientEmail: string;
  title: string;
  scope: string;
  deliverables: string;
  amount: string;
  currency: string;
  dueDate: string;
}

const EMPTY: Form = {
  clientName: "",
  clientEmail: "",
  title: "",
  scope: "",
  deliverables: "",
  amount: "",
  currency: "USD",
  dueDate: "",
};

const fromDraft = (draft: EngagementDraft): Form => ({
  clientName: draft.client_name ?? "",
  clientEmail: draft.client_email ?? "",
  title: draft.title ?? "",
  scope: draft.scope ?? "",
  deliverables: draft.deliverables.join("\n"),
  amount: draft.amount ?? "",
  currency: draft.currency ?? "USD",
  dueDate: draft.due_date ?? "",
});

const MISSING_FIELD: Record<string, keyof Form> = {
  client_name: "clientName",
  client_email: "clientEmail",
  title: "title",
  deliverables: "deliverables",
  amount: "amount",
  currency: "currency",
  due_date: "dueDate",
};

export function NewAgreementPage() {
  const navigate = useNavigate();
  const [thread, setThread] = useState("");
  const [reading, setReading] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [missing, setMissing] = useState<Set<keyof Form>>(new Set());
  const [notes, setNotes] = useState<string[]>([]);
  const [info, setInfo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const read = async (event: FormEvent) => {
    event.preventDefault();
    setReading(true);
    setInfo(null);
    try {
      const draft = await readThread(thread);
      setForm(fromDraft(draft));
      setMissing(new Set(draft.missing.map((field) => MISSING_FIELD[field]).filter(Boolean) as (keyof Form)[]));
      setNotes(draft.notes);
    } catch (failure) {
      setForm(EMPTY);
      setMissing(new Set());
      setInfo(
        statusOf(failure) === 503 || statusOf(failure) === 502
          ? errorMessage(failure, "Fill in the agreement by hand.")
          : "The thread couldn't be read. Fill in the agreement by hand.",
      );
    } finally {
      setReading(false);
    }
  };

  const set = (key: keyof Form) => (event: { target: { value: string } }) =>
    setForm((current) => (current ? { ...current, [key]: event.target.value } : current));

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    setFailed(null);
    try {
      const agreement = await createAgreement({
        client: { name: form.clientName.trim(), email: form.clientEmail.trim() },
        title: form.title.trim(),
        scope: form.scope.trim() || form.title.trim(),
        deliverables: form.deliverables.split("\n").map((line) => line.trim()).filter(Boolean),
        amount: form.amount.trim(),
        currency: form.currency,
        due_date: form.dueDate || null,
      });
      navigate(`/agreements/${agreement.id}`);
    } catch (failure) {
      setFailed(
        statusOf(failure) === 422
          ? "Check the highlighted details: the email, a fee like 800 or 800.00, and at least one deliverable."
          : errorMessage(failure, "The agreement couldn't be saved. Try again."),
      );
      setSaving(false);
    }
  };

  const field = (key: keyof Form, label: string, input: React.ReactNode, wide = false) => (
    <div className={`field${wide ? " span-2" : ""}`} data-missing={missing.has(key)}>
      <label htmlFor={key}>{label}</label>
      {input}
      {missing.has(key) && <span className="field-hint">Not in the thread. Add it.</span>}
    </div>
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1>New agreement</h1>
          <p>Paste your conversation with the client. Kweli fills in the agreement, then you check it.</p>
        </div>
      </header>

      <div className="stack">
        <form className="panel stack" onSubmit={read}>
          <div className="field">
            <label htmlFor="thread">Conversation with the client</label>
            <textarea
              id="thread"
              value={thread}
              onChange={(event) => setThread(event.target.value)}
              placeholder="Paste WhatsApp messages or an email thread where you agreed the work, price and date."
              minLength={20}
              maxLength={20000}
            />
          </div>
          <div className="row">
            <button type="submit" className="button" disabled={reading || thread.trim().length < 20}>
              {reading ? "Reading…" : "Fill in from conversation"}
            </button>
            <button type="button" className="button button-quiet" onClick={() => setForm(form ?? EMPTY)}>
              Fill in by hand
            </button>
          </div>
        </form>

        {form && (
          <form className="panel stack" onSubmit={save} aria-labelledby="review-title">
            <h2 id="review-title">Check the agreement</h2>
            {info && <p className="note note-info">{info}</p>}
            {!info && (
              <p className="muted">
                Kweli's AI filled this in from the conversation. Check every field: you're the one sending it.
              </p>
            )}
            {notes.map((note) => (
              <p className="note" key={note}>
                {note}
              </p>
            ))}
            <div className="form-grid">
              {field("clientName", "Client name", <input id="clientName" value={form.clientName} onChange={set("clientName")} required maxLength={200} />)}
              {field("clientEmail", "Client's PayPal email", <input id="clientEmail" type="email" value={form.clientEmail} onChange={set("clientEmail")} required maxLength={254} />)}
              {field("title", "Work", <input id="title" value={form.title} onChange={set("title")} required maxLength={200} />, true)}
              {field("scope", "Scope", <textarea id="scope" value={form.scope} onChange={set("scope")} maxLength={2000} style={{ minHeight: 90 }} />, true)}
              {field("deliverables", "Deliverables, one per line", <textarea id="deliverables" value={form.deliverables} onChange={set("deliverables")} required style={{ minHeight: 110 }} />, true)}
              {field("amount", "Fee", <input id="amount" inputMode="decimal" value={form.amount} onChange={set("amount")} required pattern="\d{1,9}(\.\d{1,2})?" />)}
              {field(
                "currency",
                "Currency",
                <select id="currency" value={form.currency} onChange={set("currency")}>
                  {CURRENCIES.map((code) => (
                    <option key={code}>{code}</option>
                  ))}
                </select>,
              )}
              {field("dueDate", "Due date", <input id="dueDate" type="date" value={form.dueDate} onChange={set("dueDate")} />)}
            </div>
            {failed && (
              <p className="alert" role="alert">
                {failed}
              </p>
            )}
            <div className="row">
              <button type="submit" className="button" disabled={saving}>
                {saving ? "Saving…" : "Save agreement"}
              </button>
              <span className="muted">Nothing is sent to the client until you choose to.</span>
            </div>
          </form>
        )}
      </div>
    </>
  );
}
