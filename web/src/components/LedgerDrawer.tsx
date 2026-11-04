import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { getLedgerEntry } from "../lib/api";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";
import { ProofBadge } from "./ProofBadge";
import { ProofChain } from "./ProofChain";
import { UploadDeliverable } from "./UploadDeliverable";

const RULE_NAME: Record<string, string> = {
  P1: "Invoiced",
  P2: "Amount matches",
  P3: "Paid by the client",
  P4: "Agreement accepted",
  P5: "Work delivered",
  P6: "Business payment",
  P7: "Usual amount",
};

export function LedgerDrawer({
  paymentId,
  onClose,
  onChanged,
}: {
  paymentId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { data, error, reload } = useAsync(() => getLedgerEntry(paymentId), [paymentId]);
  const closeButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const needsWork = data?.flags.some((flag) => flag.rule === "P5" && flag.status === "fail");

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} aria-hidden="true" />
      <aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
        <div className="drawer-head">
          <div>
            <h2 id="drawer-title">
              {data ? formatMoney(data.amount_minor, data.currency) : "Payment"}
            </h2>
            {data && (
              <p className="muted" style={{ margin: 0 }}>
                From {data.client}
                {data.payer && data.payer !== data.client ? `, paid by ${data.payer}` : ""}
              </p>
            )}
          </div>
          <button ref={closeButton} type="button" className="button button-quiet" onClick={onClose}>
            Close
          </button>
        </div>
        {error !== undefined && (
          <p className="alert" role="alert">
            This payment couldn't load. Close and try again.
          </p>
        )}
        {data && (
          <>
            <ProofChain
              links={data.chain.map((step) => ({
                name: step.name,
                detail: step.detail,
                state: step.proven ? "proven" : "missing",
              }))}
            />
            <ul className="rule-list" aria-label="Proof checks">
              {data.flags.map((flag) => (
                <li className="rule-item" key={flag.rule}>
                  <ProofBadge status={flag.status} />
                  <div>
                    <p>
                      <strong>{RULE_NAME[flag.rule]}.</strong> {flag.explanation}
                    </p>
                    {flag.fix && <p className="rule-fix">{flag.fix}</p>}
                  </div>
                </li>
              ))}
            </ul>
            {data.agreement_id && needsWork && (
              <UploadDeliverable
                agreementId={data.agreement_id}
                onUploaded={() => {
                  reload();
                  onChanged();
                }}
              />
            )}
            {data.agreement_id && (
              <Link to={`/agreements/${data.agreement_id}`}>Open the agreement</Link>
            )}
          </>
        )}
      </aside>
    </>
  );
}
