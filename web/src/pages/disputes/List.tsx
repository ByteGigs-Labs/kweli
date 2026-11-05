import { Link } from "react-router";
import { ProofBadge } from "../../components/ProofBadge";
import { listDisputes } from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import { dueText, OUTCOME_LABEL, STATUS_LABEL, tone } from "./shared";
import "../../styles/disputes.css";

export function DisputesPage() {
  const loaded = useAsync(listDisputes, []);
  const disputes = loaded.data;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Disputes</h1>
          <p>
            When a client opens a PayPal dispute, Kweli gathers the evidence from your records and drafts
            your response. Nothing is sent until you approve it.
          </p>
        </div>
      </header>
      {loaded.loading && <p className="muted">Loading your disputes…</p>}
      {loaded.error !== undefined && (
        <p className="alert" role="alert">
          Your disputes couldn't load. Refresh the page to try again.
        </p>
      )}
      {disputes && disputes.length === 0 && (
        <div className="empty" role="status">
          <h2>No disputes</h2>
          <p>If a client opens one, it appears here within seconds, with the evidence you already have.</p>
        </div>
      )}
      {disputes && disputes.length > 0 && (
        <ul className="dispute-rows">
          {disputes.map((dispute) => (
            <li key={dispute.id}>
              <Link to={`/disputes/${dispute.id}`} className="dispute-row">
                <ProofBadge status={tone(dispute)} />
                <span className="dispute-row-main">
                  <strong>
                    {formatMoney(dispute.amount_minor, dispute.currency)} · {dispute.client ?? "Unknown client"}
                  </strong>
                  <span>
                    {dispute.reason_label} ·{" "}
                    {dispute.outcome
                      ? (OUTCOME_LABEL[dispute.outcome] ?? "Resolved")
                      : dispute.submitted_at
                        ? "Evidence sent"
                        : (STATUS_LABEL[dispute.status] ?? dispute.status)}
                  </span>
                </span>
                <span className="dispute-row-side">
                  {dispute.source === "seed" && <span className="source-tag source-standard">Demo</span>}
                  {!dispute.outcome && !dispute.submitted_at && (
                    <span className="muted">{dueText(dispute.evidence_due_at)}</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
