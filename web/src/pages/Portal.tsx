import { useState } from "react";
import { useParams } from "react-router";
import { Wordmark } from "../components/Wordmark";
import { acceptPortal, errorMessage, viewPortal } from "../lib/api";
import { shortDate } from "../lib/dates";
import { useAsync } from "../lib/useAsync";
import "../styles/portal.css";

export function PortalPage() {
  const { token = "" } = useParams();
  const { data, setData, error, loading } = useAsync(() => viewPortal(token), [token]);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const accept = async () => {
    setBusy(true);
    setFailed(null);
    try {
      setData(await acceptPortal(token));
    } catch (failure) {
      setFailed(errorMessage(failure, "Your acceptance couldn't be saved. Try again."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="portal">
      <header className="portal-head">
        <Wordmark />
      </header>
      <main className="portal-body">
        {loading && <p className="muted">Loading…</p>}
        {error !== undefined && (
          <section className="panel">
            <h1>This link doesn't work</h1>
            <p>{errorMessage(error, "Ask the freelancer to send you a new link.")}</p>
          </section>
        )}
        {data && (
          <article className="panel stack" aria-labelledby="portal-title">
            <div>
              <p className="muted" style={{ margin: 0 }}>
                Agreement from {data.freelancer}
              </p>
              <h1 id="portal-title">{data.title}</h1>
            </div>
            <dl className="facts">
              <dt>For</dt>
              <dd>{data.client}</dd>
              <dt>Fee</dt>
              <dd>
                {data.currency} {data.amount}
              </dd>
              <dt>Due</dt>
              <dd>{shortDate(data.due_date) || "To be agreed"}</dd>
            </dl>
            <section>
              <h2>Deliverables</h2>
              <ul className="terms">
                {data.deliverables.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
            <section>
              <h2>Terms</h2>
              <ol className="terms">
                {data.terms.map((term) => (
                  <li key={term}>{term}</li>
                ))}
              </ol>
            </section>
            {data.status === "accepted" ? (
              <p className="portal-done" role="status">
                You accepted this agreement on {shortDate(data.accepted_at)}. {data.freelancer} will
                send the PayPal invoice.
              </p>
            ) : (
              <div className="stack">
                <label className="check">
                  <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                  <span>
                    I'm accepting for {data.client}, and the PayPal payment will come from us.
                  </span>
                </label>
                {failed && (
                  <p className="alert" role="alert">
                    {failed}
                  </p>
                )}
                <button type="button" className="button" disabled={!confirmed || busy} onClick={accept}>
                  {busy ? "Saving…" : "Accept agreement"}
                </button>
              </div>
            )}
          </article>
        )}
      </main>
    </div>
  );
}
