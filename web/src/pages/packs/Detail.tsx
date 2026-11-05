import { useState } from "react";
import { Link, useParams } from "react-router";
import { ProofBadge } from "../../components/ProofBadge";
import { editPackLetter, errorMessage, errorProblems, getPack, openDocument } from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import type { LetterProblem, Pack, ProofStatus } from "../../types";
import { longDate, SOURCE_LABEL } from "./List";
import "../../styles/packs.css";

const CITATION = /(\[[A-Z]\d+(?:\s*,\s*[A-Z]\d+)*\])/;
const IS_CITATION = /^\[[A-Z]\d+(?:\s*,\s*[A-Z]\d+)*\]$/;

function Letter({ text }: { text: string }) {
  return (
    <div className="pack-letter">
      {text.split("\n").map((line, index) =>
        line.trim() === "" ? (
          <br key={index} />
        ) : (
          <p key={index}>
            {line.split(CITATION).map((part, at) =>
              IS_CITATION.test(part) ? (
                <mark key={at} className="cite">
                  {part}
                </mark>
              ) : (
                <span key={at}>{part}</span>
              ),
            )}
          </p>
        ),
      )}
    </div>
  );
}

function Problems({ items, title }: { items: LetterProblem[]; title: string }) {
  return (
    <div className="pack-problems" role="alert">
      <p>
        <strong>{title}</strong>
      </p>
      <ul>
        {items.map((problem, index) => (
          <li key={index}>
            {problem.message}
            {problem.excerpt && <span className="muted"> “{problem.excerpt}”</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const STATUS_ORDER: { status: ProofStatus; label: string }[] = [
  { status: "pass", label: "fully proven" },
  { status: "warn", label: "need attention" },
  { status: "fail", label: "missing proof" },
  { status: "pending", label: "being checked" },
];

function Editor({ pack, onSaved }: { pack: Pack; onSaved: (pack: Pack) => void }) {
  const [text, setText] = useState(pack.letter);
  const [busy, setBusy] = useState(false);
  const [problems, setProblems] = useState<LetterProblem[]>([]);
  const [failed, setFailed] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setProblems([]);
    setFailed(null);
    try {
      onSaved(await editPackLetter(pack.id, text));
    } catch (failure) {
      const found = errorProblems(failure);
      if (found.length) setProblems(found);
      else setFailed(errorMessage(failure, "The letter couldn't be saved. Try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div className="field">
        <label htmlFor="pack-letter">Letter text</label>
        <textarea
          id="pack-letter"
          rows={18}
          value={text}
          onChange={(event) => setText(event.target.value)}
          spellCheck
        />
      </div>
      <p className="muted">
        Keep the references in square brackets. Kweli checks every citation and amount again before it
        rebuilds the PDF and ZIP.
      </p>
      {problems.length > 0 && (
        <Problems items={problems} title="Not saved. Fix these and try again:" />
      )}
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
      <div>
        <button type="button" className="button" onClick={save} disabled={busy || !text.trim()}>
          {busy ? "Checking…" : "Check and save"}
        </button>
      </div>
    </div>
  );
}

export function PackDetailPage() {
  const { id = "" } = useParams();
  const loaded = useAsync(() => getPack(id), [id]);
  const [editing, setEditing] = useState(false);
  const pack = loaded.data;

  return (
    <>
      <p className="back-link">
        <Link to="/packs">All packs</Link>
      </p>
      {loaded.loading && <p className="muted">Loading the pack…</p>}
      {loaded.error !== undefined && (
        <p className="alert" role="alert">
          This pack couldn't load.
        </p>
      )}
      {pack && (
        <>
          <header className="page-head">
            <div>
              <h1>
                Pack for {longDate(pack.period_start)} – {longDate(pack.period_end)}
              </h1>
              <p>
                {pack.summary.payments} payments from {pack.summary.clients} client
                {pack.summary.clients === 1 ? "" : "s"},{" "}
                {pack.totals.map((total) => formatMoney(total.amount_minor, total.currency)).join(", ")}{" "}
                in total. {pack.summary.attached} documents attached.
              </p>
            </div>
          </header>

          <section className="pack-downloads" aria-label="Downloads">
            <button
              type="button"
              className="button"
              disabled={!pack.pdf_document_id}
              onClick={() => pack.pdf_document_id && openDocument(pack.pdf_document_id)}
            >
              Download PDF
            </button>
            <button
              type="button"
              className="button button-quiet"
              disabled={!pack.zip_document_id}
              onClick={() => pack.zip_document_id && openDocument(pack.zip_document_id)}
            >
              Download ZIP with documents
            </button>
            <ul className="pack-facts" aria-label="Proof in this pack">
              {STATUS_ORDER.filter((item) => pack.statuses[item.status]).map((item) => (
                <li key={item.status}>
                  <ProofBadge status={item.status} /> {pack.statuses[item.status]} {item.label}
                </li>
              ))}
            </ul>
          </section>

          {pack.summary.left_out.length > 0 && (
            <p className="alert" role="status">
              {pack.summary.left_out.join(", ")} were too large for this pack and are listed but not
              attached.
            </p>
          )}

          <section className="pack-letter-card" aria-labelledby="letter-title">
            <div className="pack-letter-head">
              <h2 id="letter-title">Cover letter</h2>
              <span className={`source-tag source-${pack.letter_source}`}>
                {SOURCE_LABEL[pack.letter_source]}
              </span>
              {!editing && (
                <button type="button" className="button button-quiet" onClick={() => setEditing(true)}>
                  Edit the letter
                </button>
              )}
            </div>
            {pack.letter_source === "standard" && pack.summary.ai_rejected.length > 0 && (
              <details className="pack-rejected">
                <summary>Why Kweli didn't use the AI's draft</summary>
                <Problems
                  items={pack.summary.ai_rejected}
                  title="The AI's draft failed the citation checks, so Kweli used its standard letter:"
                />
              </details>
            )}
            {editing ? (
              <Editor
                pack={pack}
                onSaved={(saved) => {
                  loaded.setData(saved);
                  setEditing(false);
                }}
              />
            ) : (
              <Letter text={pack.letter} />
            )}
          </section>

          <details className="score-explainer">
            <summary>How Kweli checks the letter</summary>
            <p>
              Every reference in square brackets must point to a payment or document in this pack. Every
              amount must be a real payment, invoice, agreement fee or total, and a sentence that names an
              amount must cite where it comes from. An amount can't be pinned on the wrong payment, and the
              letter can't contain links or email addresses that aren't in your records.
            </p>
            <p className="muted">
              PDF SHA-256 {pack.summary.pdf_sha256.slice(0, 16)}… · ZIP SHA-256{" "}
              {pack.summary.zip_sha256.slice(0, 16)}… · Audit head {pack.summary.audit_head.slice(7, 23)}…
            </p>
          </details>
        </>
      )}
    </>
  );
}
