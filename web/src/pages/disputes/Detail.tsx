import { useState } from "react";
import { Link, useParams } from "react-router";
import { ProofBadge } from "../../components/ProofBadge";
import {
  approveDispute,
  editDisputeResponse,
  errorMessage,
  errorProblems,
  getDispute,
  needsPro,
  prepareDispute,
  refreshDispute,
  sandboxDispute,
  submitDispute,
} from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import type { Dispute, DisputeEvidence, LetterProblem, ProofStatus } from "../../types";
import { dueText, OUTCOME_LABEL, STATUS_LABEL } from "./shared";
import "../../styles/disputes.css";

const EVIDENCE_BADGE: Record<DisputeEvidence["status"], ProofStatus> = {
  ready: "pass",
  partial: "warn",
  missing: "fail",
};

const STRENGTH: Record<Dispute["strength"], { label: string; text: string }> = {
  strong: { label: "Strong case", text: "Every piece of evidence for this kind of dispute is on file." },
  fair: { label: "Fair case", text: "Some evidence is incomplete. It's still worth responding." },
  weak: { label: "Weak case", text: "Some evidence is missing. Add it before you respond, if you can." },
};

const SOURCE: Record<string, string> = {
  ai: "Drafted by AI, checked",
  standard: "Kweli standard response",
  edited: "Edited by you, checked",
};

function Evidence({ item, agreementId }: { item: DisputeEvidence; agreementId: string | null }) {
  return (
    <li className="evidence-item">
      <ProofBadge status={EVIDENCE_BADGE[item.status]} />
      <div className="evidence-body">
        <p>
          <strong>{item.label}.</strong> {item.detail}
        </p>
        <p className="muted evidence-why">{item.why}</p>
        {item.files.length > 0 && (
          <p className="evidence-files">
            Attaches: {item.files.map((file) => file.name).join(", ")}
          </p>
        )}
        {item.notes.map((note) => (
          <p key={note} className="muted evidence-why">
            {note}
          </p>
        ))}
        {item.fix && (
          <p className="rule-fix">
            {item.fix}{" "}
            {item.key === "work" && agreementId && <Link to={`/agreements/${agreementId}`}>Open the agreement</Link>}
          </p>
        )}
      </div>
    </li>
  );
}

function ProblemList({ items }: { items: LetterProblem[] }) {
  return (
    <div className="pack-problems" role="alert">
      <p>
        <strong>Not saved. Fix these and try again:</strong>
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

function Respond({
  dispute,
  token,
  onChange,
}: {
  dispute: Dispute;
  token: string | null;
  onChange: (dispute: Dispute) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(dispute.response ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [problems, setProblems] = useState<LetterProblem[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [upgrade, setUpgrade] = useState(false);

  const run = async (label: string, action: () => Promise<Dispute>) => {
    setBusy(label);
    setFailed(null);
    setProblems([]);
    try {
      const next = await action();
      onChange(next);
      return next;
    } catch (failure) {
      const found = errorProblems(failure);
      setUpgrade(needsPro(failure));
      if (found.length) setProblems(found);
      else setFailed(errorMessage(failure, "That didn't work. Try again."));
      return null;
    } finally {
      setBusy(null);
    }
  };

  const fileCount = dispute.evidence.reduce((total, item) => total + item.files.length, 0);
  const paypalTakesEvidence = dispute.allowed.includes("provide_evidence");

  if (!dispute.response) {
    return (
      <div className="stack">
        <p>Kweli will write the response from the evidence above, then check every amount in it.</p>
        <div>
          <button
            type="button"
            className="button"
            disabled={busy !== null}
            onClick={() => run("prepare", () => prepareDispute(dispute.id))}
          >
            {busy ? "Preparing…" : "Prepare the response"}
          </button>
        </div>
        {failed && (
          <p className="alert" role="alert">
            {failed} {upgrade && <Link to="/billing">See Kweli Pro</Link>}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="pack-letter-head">
        <h3>Your response</h3>
        {dispute.response_source && (
          <span className={`source-tag source-${dispute.response_source}`}>
            {SOURCE[dispute.response_source]}
          </span>
        )}
        {!editing && (
          <button
            type="button"
            className="button button-quiet"
            onClick={() => {
              setText(dispute.response ?? "");
              setEditing(true);
              setConfirming(false);
            }}
          >
            Edit
          </button>
        )}
      </div>
      {dispute.response_source === "standard" && dispute.rejected.length > 0 && (
        <details className="pack-rejected">
          <summary>Why Kweli didn't use the AI's draft</summary>
          <ul>
            {dispute.rejected.map((problem, index) => (
              <li key={index}>{problem.message}</li>
            ))}
          </ul>
        </details>
      )}
      {editing ? (
        <>
          <div className="field">
            <label htmlFor="dispute-response">Response text</label>
            <textarea
              id="dispute-response"
              rows={9}
              maxLength={2200}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </div>
          <p className="muted">{text.length} of 2,000 characters. PayPal's reviewer reads this.</p>
          {problems.length > 0 && <ProblemList items={problems} />}
          <div className="row-actions">
            <button
              type="button"
              className="button"
              disabled={busy !== null || !text.trim()}
              onClick={async () => {
                const saved = await run("save", () => editDisputeResponse(dispute.id, text));
                if (saved) setEditing(false);
              }}
            >
              {busy === "save" ? "Checking…" : "Check and save"}
            </button>
            <button type="button" className="button button-quiet" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </>
      ) : (
        <blockquote className="dispute-response">{dispute.response}</blockquote>
      )}

      {!editing && (
        <section className="approve-box" aria-labelledby="approve-title">
          <h3 id="approve-title">Approve and send</h3>
          <p>
            Sends this response and {fileCount} file{fileCount === 1 ? "" : "s"} to PayPal for dispute{" "}
            {dispute.paypal_dispute_id}. You can't take it back.
          </p>
          {dispute.source === "seed" && (
            <p className="muted">This is a demo dispute, so Kweli won't send anything to PayPal.</p>
          )}
          {!paypalTakesEvidence && dispute.source !== "seed" && (
            <p className="muted">
              PayPal isn't accepting evidence for this dispute right now ({STATUS_LABEL[dispute.status] ?? dispute.status}).
            </p>
          )}
          {failed && (
            <p className="alert" role="alert">
              {failed}
            </p>
          )}
          {confirming ? (
            <div className="row-actions">
              <button
                type="button"
                className="button"
                disabled={busy !== null}
                onClick={async () => {
                  const approved = token ? null : await run("approve", () => approveDispute(dispute.id));
                  const live = token ?? approved?.approval_token;
                  if (live) await run("submit", () => submitDispute(dispute.id, live));
                  setConfirming(false);
                }}
              >
                {busy ? "Sending to PayPal…" : "Yes, send it to PayPal"}
              </button>
              <button type="button" className="button button-quiet" onClick={() => setConfirming(false)}>
                Not yet
              </button>
            </div>
          ) : (
            <div>
              <button
                type="button"
                className="button"
                disabled={busy !== null || (!paypalTakesEvidence && dispute.source !== "seed")}
                onClick={() => setConfirming(true)}
              >
                Approve and send
              </button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function SandboxTools({ dispute, onChange }: { dispute: Dispute; onChange: (dispute: Dispute) => void }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const act = async (action: () => Promise<Dispute>) => {
    setBusy(true);
    setFailed(null);
    try {
      onChange(await action());
    } catch (failure) {
      setFailed(errorMessage(failure, "PayPal's sandbox refused that. Refresh and check the status."));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="sandbox-tools" aria-labelledby="sandbox-title">
      <h2 id="sandbox-title">Sandbox tools</h2>
      <p className="muted">
        Only in PayPal's sandbox: move the dispute along to see the whole lifecycle. PayPal allows these
        while the dispute is under review.
      </p>
      <div className="row-actions">
        <button type="button" className="button button-quiet" disabled={busy} onClick={() => act(() => refreshDispute(dispute.id))}>
          Refresh from PayPal
        </button>
        <button
          type="button"
          className="button button-quiet"
          disabled={busy || !dispute.allowed.includes("require_evidence")}
          onClick={() => act(() => sandboxDispute(dispute.id, "require_evidence"))}
        >
          Ask me for evidence
        </button>
        <button
          type="button"
          className="button button-quiet"
          disabled={busy || !dispute.allowed.includes("adjudicate")}
          onClick={() => act(() => sandboxDispute(dispute.id, "seller_favor"))}
        >
          Decide in my favour
        </button>
        <button
          type="button"
          className="button button-quiet"
          disabled={busy || !dispute.allowed.includes("adjudicate")}
          onClick={() => act(() => sandboxDispute(dispute.id, "buyer_favor"))}
        >
          Decide for the client
        </button>
      </div>
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
    </section>
  );
}

export function DisputeDetailPage() {
  const { id = "" } = useParams();
  const loaded = useAsync(() => getDispute(id), [id]);
  const [token, setToken] = useState<string | null>(null);
  const dispute = loaded.data;

  const update = (next: Dispute) => {
    setToken(next.approval_token);
    loaded.setData(next);
  };

  return (
    <>
      <p className="back-link">
        <Link to="/disputes">All disputes</Link>
      </p>
      {loaded.loading && <p className="muted">Loading the dispute…</p>}
      {loaded.error !== undefined && (
        <p className="alert" role="alert">
          This dispute couldn't load.
        </p>
      )}
      {dispute && (
        <>
          <header className="page-head">
            <div>
              <h1>
                {formatMoney(dispute.amount_minor, dispute.currency)} · {dispute.client ?? "Unknown client"}
              </h1>
              <p>
                {dispute.reason_label}. {STATUS_LABEL[dispute.status] ?? dispute.status}
                {dispute.stage ? ` (${dispute.stage.toLowerCase().replace(/_/g, " ")} stage)` : ""}.{" "}
                {!dispute.submitted_at && dispute.status !== "RESOLVED" && dueText(dispute.evidence_due_at)}
              </p>
            </div>
          </header>

          {dispute.outcome && (
            <p className={`outcome outcome-${dispute.outcome === "RESOLVED_SELLER_FAVOUR" ? "won" : "other"}`} role="status">
              {OUTCOME_LABEL[dispute.outcome] ?? "Resolved"}
            </p>
          )}

          {dispute.buyer_messages.length > 0 && (
            <section className="dispute-card" aria-labelledby="claim-title">
              <h2 id="claim-title">What the client said</h2>
              {dispute.buyer_messages.map((message, index) => (
                <blockquote key={index} className="buyer-message">
                  {message.content}
                </blockquote>
              ))}
            </section>
          )}

          <section className="dispute-card" aria-labelledby="evidence-title">
            <div className="pack-letter-head">
              <h2 id="evidence-title">Evidence</h2>
              <span className={`strength strength-${dispute.strength}`}>{STRENGTH[dispute.strength].label}</span>
            </div>
            <p className="muted">{STRENGTH[dispute.strength].text}</p>
            <ul className="evidence-list">
              {dispute.evidence.map((item) => (
                <Evidence key={item.key} item={item} agreementId={dispute.agreement_id} />
              ))}
            </ul>
          </section>

          <section className="dispute-card" aria-labelledby="respond-title">
            <h2 id="respond-title">Respond</h2>
            {dispute.submitted_at && dispute.submission ? (
              <div className="stack">
                <p>
                  <strong>Sent to PayPal</strong> on{" "}
                  {new Date(dispute.submitted_at).toLocaleString("en-GB", {
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}{" "}
                  with {dispute.submission.files.length} files.
                </p>
                <ul className="evidence-sent">
                  {dispute.submission.files.map((file) => (
                    <li key={file.name}>
                      {file.name} <span className="muted">SHA-256 {file.sha256.slice(0, 12)}…</span>
                    </li>
                  ))}
                </ul>
                {dispute.response && <blockquote className="dispute-response">{dispute.response}</blockquote>}
              </div>
            ) : dispute.status === "RESOLVED" ? (
              <p className="muted">This dispute is closed.</p>
            ) : (
              <Respond key={dispute.response ?? "none"} dispute={dispute} token={token} onChange={update} />
            )}
          </section>

          {dispute.sandbox_tools && <SandboxTools dispute={dispute} onChange={update} />}
        </>
      )}
    </>
  );
}
