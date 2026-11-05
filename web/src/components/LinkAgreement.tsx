import { useState } from "react";
import { errorMessage, linkPaymentAgreement, listAgreements } from "../lib/api";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";

export function LinkAgreement({
  paymentId,
  current,
  onLinked,
}: {
  paymentId: string;
  current: string | null;
  onLinked: () => void;
}) {
  const agreements = useAsync(listAgreements, []);
  const [choice, setChoice] = useState(current ?? "");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const save = async (agreementId: string | null) => {
    setBusy(true);
    setFailed(null);
    try {
      await linkPaymentAgreement(paymentId, agreementId);
      onLinked();
    } catch (failure) {
      setFailed(errorMessage(failure, "The link couldn't be saved. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const options = agreements.data ?? [];

  return (
    <section className="link-agreement" aria-labelledby="link-agreement-title">
      <h3 id="link-agreement-title">{current ? "Linked by hand" : "Link to an agreement"}</h3>
      <p className="muted">
        This payment didn't come through a Kweli invoice. Link it to the agreement for this work so
        Kweli can check the payer and the delivered work.
      </p>
      {agreements.error !== undefined && (
        <p className="alert" role="alert">
          Your agreements couldn't load.
        </p>
      )}
      {agreements.data && options.length === 0 && (
        <p className="muted">You have no agreements yet. Create one from the Agreements page.</p>
      )}
      {options.length > 0 && (
        <div className="link-agreement-row">
          <label className="visually-hidden" htmlFor="link-agreement-select">
            Agreement
          </label>
          <select
            id="link-agreement-select"
            value={choice}
            onChange={(event) => setChoice(event.target.value)}
            disabled={busy}
          >
            <option value="">Choose an agreement…</option>
            {options.map((agreement) => (
              <option key={agreement.id} value={agreement.id}>
                {agreement.client.name}: {agreement.title} (
                {formatMoney(agreement.amount_minor, agreement.currency)})
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button"
            disabled={busy || !choice || choice === current}
            onClick={() => save(choice)}
          >
            {busy ? "Saving…" : "Link"}
          </button>
          {current && (
            <button
              type="button"
              className="button button-quiet"
              disabled={busy}
              onClick={() => save(null)}
            >
              Unlink
            </button>
          )}
        </div>
      )}
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
    </section>
  );
}
