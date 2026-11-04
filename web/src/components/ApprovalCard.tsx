import { useState } from "react";
import { approveAction, errorMessage, rejectAction } from "../lib/api";
import type { AgentAction } from "../types";

const DONE: Record<string, string> = {
  executed: "Done",
  failed: "Didn't go through",
  rejected: "Declined",
  approved: "Working…",
};

export function ApprovalCard({ action: initial }: { action: AgentAction }) {
  const [action, setAction] = useState(initial);
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const decide = async (choice: "approve" | "reject") => {
    setBusy(choice);
    setFailed(null);
    try {
      setAction(
        choice === "approve" && action.token
          ? await approveAction(action.id, action.token)
          : await rejectAction(action.id),
      );
    } catch (failure) {
      setFailed(errorMessage(failure, "That didn't work. Try again."));
    } finally {
      setBusy(null);
    }
  };

  const open = action.status === "proposed";
  const expires = new Date(action.expires_at).toLocaleTimeString("en-KE", {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <section className={`approval approval-${action.status}`} aria-label={`Approval: ${action.title}`}>
      <div className="approval-head">
        <h3>{action.title}</h3>
        {!open && <span className={`chip chip-${action.status === "executed" ? "done" : action.status === "failed" ? "stop" : "quiet"}`}>{DONE[action.status]}</span>}
      </div>
      <dl className="facts">
        {action.details.map((detail) => (
          <div key={detail.label} style={{ display: "contents" }}>
            <dt>{detail.label}</dt>
            <dd>{detail.value}</dd>
          </div>
        ))}
      </dl>
      {open ? (
        <>
          <div className="row">
            <button type="button" className="button" disabled={busy !== null} onClick={() => decide("approve")}>
              {busy === "approve" ? "Working…" : "Approve"}
            </button>
            <button type="button" className="button button-quiet" disabled={busy !== null} onClick={() => decide("reject")}>
              Decline
            </button>
          </div>
          <p className="muted approval-note">
            Nothing happens until you approve. This expires at {expires}.
          </p>
        </>
      ) : (
        action.result?.message && (
          <p className="approval-result" role="status">
            {action.result.message}{" "}
            {action.result.link && (
              <a href={action.result.link} target="_blank" rel="noreferrer noopener">
                Open link
              </a>
            )}
          </p>
        )
      )}
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
    </section>
  );
}
