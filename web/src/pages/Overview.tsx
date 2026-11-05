import { Link, useNavigate } from "react-router";
import { ProofBadge } from "../components/ProofBadge";
import { BAND_LABEL, ScoreMeter } from "../components/ScoreMeter";
import { getReadiness, listDisputes } from "../lib/api";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";
import { dueText } from "./disputes/shared";
import type { DisputeSummary, FixItem, Readiness } from "../types";
import "../styles/overview.css";

const RULE_NAME: Record<string, string> = {
  P1: "Invoiced",
  P2: "Amount matches",
  P3: "Paid by the client",
  P4: "Agreement accepted",
  P5: "Work delivered",
  P6: "Business payment",
};

const dayMonth = (value: string) =>
  new Date(value).toLocaleDateString("en-KE", { day: "numeric", month: "short" });

function summary(readiness: Readiness) {
  const { checks, payments } = readiness;
  const scored = checks.pass + checks.warn + checks.fail;
  const paymentsText = `${payments} payment${payments === 1 ? "" : "s"}`;
  return `${checks.pass} of ${scored} checks pass across ${paymentsText}.`;
}

function nextStep(readiness: Readiness) {
  const count = readiness.fix_total;
  if (count === 0) return "Every payment has its proof. Keep it that way as new payments arrive.";
  const which = count === 1 ? "One payment has" : `${count} payments have`;
  return `${which} something to fix. Start at the top of the list: it matters most.`;
}

function FixCard({ item, rank }: { item: FixItem; rank: number }) {
  const navigate = useNavigate();
  return (
    <li className="fix-card">
      <span className="fix-rank" aria-hidden="true">
        {rank}
      </span>
      <div className="fix-body">
        <div className="fix-head">
          <ProofBadge status={item.status} />
          <h3>
            {item.client} · {formatMoney(item.amount_minor, item.currency)}
          </h3>
          <span className="muted">Paid {dayMonth(item.received_at)}</span>
          {item.points > 0 && <span className="fix-points">+{item.points} points</span>}
        </div>
        <ol className="fix-steps">
          {item.steps.map((step) => (
            <li key={step.rule}>
              <p>
                <strong>{RULE_NAME[step.rule] ?? step.rule}.</strong> {step.problem}
              </p>
              <p className="rule-fix">{step.fix}</p>
            </li>
          ))}
        </ol>
        <button
          type="button"
          className="button"
          onClick={() => navigate(`/ledger?payment=${encodeURIComponent(item.payment_id)}`)}
        >
          Fix this payment
        </button>
      </div>
    </li>
  );
}

function OpenDisputes({ disputes }: { disputes: DisputeSummary[] }) {
  const open = disputes.filter(
    (d) => d.status === "WAITING_FOR_SELLER_RESPONSE" && !d.submitted_at && !d.outcome,
  );
  const first = open[0];
  if (!first) return null;
  return (
    <section className="dispute-alert" aria-labelledby="dispute-alert-title">
      <h2 id="dispute-alert-title">
        {open.length === 1 ? "A client opened a dispute" : `${open.length} disputes need your response`}
      </h2>
      <p>
        {formatMoney(first.amount_minor, first.currency)} from {first.client ?? "a client"}: {first.reason_label.toLowerCase()}.{" "}
        {dueText(first.evidence_due_at)}. Kweli has already gathered the evidence.
      </p>
      <Link className="button" to={open.length === 1 ? `/disputes/${first.id}` : "/disputes"}>
        {open.length === 1 ? "Respond to the dispute" : "See the disputes"}
      </Link>
    </section>
  );
}

export function OverviewPage() {
  const loaded = useAsync(getReadiness, []);
  const disputes = useAsync(listDisputes, []);
  const readiness = loaded.data;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Overview</h1>
          <p>How ready you are if PayPal asks what your payments were for.</p>
        </div>
      </header>

      {loaded.error !== undefined && (
        <p className="alert" role="alert">
          Your readiness couldn't load. Refresh the page to try again.
        </p>
      )}
      {loaded.loading && <p className="muted">Checking your proof…</p>}
      {disputes.data && <OpenDisputes disputes={disputes.data} />}

      {readiness && readiness.band === "no_payments" && (
        <div className="empty" role="status">
          <h2>No payments yet</h2>
          <p>
            Your score appears once a client pays. Start with an <Link to="/agreements/new">agreement</Link>{" "}
            so the first payment arrives with its proof.
          </p>
        </div>
      )}

      {readiness && readiness.band !== "no_payments" && (
        <>
          <section className={`readiness-card band-${readiness.band}`} aria-labelledby="readiness-title">
            <ScoreMeter score={readiness.score} band={readiness.band} />
            <div className="readiness-text">
              <h2 id="readiness-title">{BAND_LABEL[readiness.band]}</h2>
              <p>
                {summary(readiness)} {nextStep(readiness)}
              </p>
              <ul className="readiness-facts">
                {readiness.statuses.fail > 0 && (
                  <li>
                    <ProofBadge status="fail" /> {readiness.statuses.fail} missing proof
                  </li>
                )}
                {readiness.statuses.warn > 0 && (
                  <li>
                    <ProofBadge status="warn" /> {readiness.statuses.warn} need attention
                  </li>
                )}
                {readiness.statuses.pending > 0 && (
                  <li>
                    <ProofBadge status="pending" /> {readiness.statuses.pending} being checked by PayPal
                  </li>
                )}
                <li>
                  <ProofBadge status="pass" /> {readiness.statuses.pass} fully proven
                </li>
              </ul>
              {readiness.large_payments > 0 && (
                <p className="muted readiness-note">
                  {readiness.large_payments === 1 ? "One payment is" : `${readiness.large_payments} payments are`}{" "}
                  much larger than usual. Large payments get a closer look, so keep their proof complete.
                </p>
              )}
              <p className="readiness-links">
                <Link to="/ledger?view=clients">See readiness by client</Link>
                <Link to="/ledger">Open the proof ledger</Link>
              </p>
            </div>
          </section>

          <section aria-labelledby="fix-title" className="fix-section">
            <h2 id="fix-title">Fix next</h2>
            {readiness.fix_next.length === 0 ? (
              <p className="muted">Nothing to fix. Every payment has its proof on file.</p>
            ) : (
              <ol className="fix-list">
                {readiness.fix_next.map((item, index) => (
                  <FixCard key={item.payment_id} item={item} rank={index + 1} />
                ))}
              </ol>
            )}
            {readiness.fix_total > readiness.fix_next.length && (
              <p className="muted">
                Showing the first {readiness.fix_next.length} of {readiness.fix_total}.{" "}
                <Link to="/ledger?status=fail">See them all in the ledger</Link>.
              </p>
            )}
          </section>

          <details className="score-explainer">
            <summary>How the score works</summary>
            <p>
              Each payment gets six proof checks. A check on file counts as a full point, one that needs
              attention counts as half, and a missing one counts as nothing. Checks still waiting on PayPal
              aren't counted. The score is the share of points you have, out of 100.
            </p>
            <p>
              "Ready" needs {readiness.thresholds.ready} or more and no payment with missing proof, because a
              single unexplained payment can be enough to start a review. The unusual-amount check is shown as
              advice and isn't scored.
            </p>
          </details>
        </>
      )}
    </>
  );
}
