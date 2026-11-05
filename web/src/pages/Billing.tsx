import { useGetIdentity } from "@refinedev/core";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { cancelBilling, confirmBilling, errorMessage, getBilling, startCheckout } from "../lib/api";
import { useAsync } from "../lib/useAsync";
import "../styles/billing.css";

const SUBSCRIPTION_ID = /^[A-Za-z0-9-]{3,64}$/;

export function BillingPage() {
  const loaded = useAsync(getBilling, []);
  const billing = loaded.data;
  const { refetch } = useGetIdentity();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const confirming = useRef(false);

  const returned = params.get("paypal");
  const subscriptionId = params.get("subscription_id");

  const badReference = returned === "approved" && !!subscriptionId && !SUBSCRIPTION_ID.test(subscriptionId);

  useEffect(() => {
    if (returned !== "approved" || !subscriptionId || badReference || confirming.current) return;
    confirming.current = true;
    setBusy("confirm");
    confirmBilling(subscriptionId)
      .then((next) => {
        loaded.setData(next);
        setNote(next.plan === "pro" ? "Welcome to Kweli Pro." : "PayPal hasn't activated it yet. Refresh in a minute.");
        refetch();
      })
      .catch((failure) => setFailed(errorMessage(failure, "Kweli couldn't confirm the subscription.")))
      .finally(() => {
        setBusy(null);
        setParams({}, { replace: true });
      });
  }, [returned, subscriptionId, badReference, setParams, loaded, refetch]);

  const upgrade = async () => {
    setBusy("upgrade");
    setFailed(null);
    try {
      const { approve_url } = await startCheckout();
      const url = new URL(approve_url);
      if (url.protocol !== "https:" || !/(^|\.)paypal\.com$/.test(url.hostname)) {
        throw new Error("Unexpected checkout address");
      }
      window.location.assign(url.toString());
    } catch (failure) {
      setFailed(errorMessage(failure, "PayPal checkout couldn't start. Try again."));
      setBusy(null);
    }
  };

  const cancel = async () => {
    setBusy("cancel");
    setFailed(null);
    try {
      loaded.setData(await cancelBilling());
      setNote("Your subscription is cancelled. You're back on the free plan.");
      refetch();
    } catch (failure) {
      setFailed(errorMessage(failure, "The subscription couldn't be cancelled. Try again."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Billing</h1>
          <p>Kweli Pro is a monthly subscription through PayPal. Cancel any time.</p>
        </div>
      </header>
      {returned === "cancelled" && (
        <p className="billing-note" role="status">
          You left PayPal before subscribing. Nothing was charged.
        </p>
      )}
      {badReference && (
        <p className="alert" role="alert">
          PayPal sent back an unexpected subscription reference.
        </p>
      )}
      {note && (
        <p className="billing-note" role="status">
          {note}
        </p>
      )}
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
      {loaded.loading && <p className="muted">Loading your plan…</p>}
      {loaded.error !== undefined && (
        <p className="alert" role="alert">
          Billing couldn't load.
        </p>
      )}
      {billing && (
        <div className="plans">
          <section className={`plan-card${billing.plan === "free" ? " plan-current" : ""}`} aria-labelledby="free-title">
            <h2 id="free-title">Free</h2>
            <p className="plan-price">
              <strong>{billing.currency} 0</strong>
            </p>
            <ul>
              <li>Proof ledger and readiness score</li>
              <li>Agreements, invoices and the assistant</li>
              <li>Up to {billing.free_client_limit} clients</li>
            </ul>
            {billing.plan === "free" && <p className="plan-tag">Your plan</p>}
          </section>
          <section className={`plan-card${billing.plan === "pro" ? " plan-current" : ""}`} aria-labelledby="pro-title">
            <h2 id="pro-title">Kweli Pro</h2>
            <p className="plan-price">
              <strong>
                {billing.currency} {billing.price}
              </strong>{" "}
              a month
            </p>
            <ul>
              {billing.features.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            {billing.plan === "pro" ? (
              <>
                <p className="plan-tag">Your plan</p>
                {billing.next_billing_at && (
                  <p className="muted">
                    Next payment{" "}
                    {new Date(billing.next_billing_at).toLocaleDateString("en-GB", {
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    })}
                  </p>
                )}
                {billing.enabled && billing.subscription_status && (
                  <button type="button" className="button button-quiet" disabled={busy !== null} onClick={cancel}>
                    {busy === "cancel" ? "Cancelling…" : "Cancel subscription"}
                  </button>
                )}
                {!billing.enabled && <p className="muted">Billing isn't switched on here, so every feature is open.</p>}
              </>
            ) : (
              <button type="button" className="button" disabled={busy !== null || !billing.enabled} onClick={upgrade}>
                {busy === "upgrade" ? "Opening PayPal…" : busy === "confirm" ? "Confirming…" : "Upgrade with PayPal"}
              </button>
            )}
          </section>
        </div>
      )}
      <p className="muted billing-fine">
        You approve the subscription on PayPal's own page. Kweli never sees your card or PayPal login, and
        checks the subscription with PayPal before switching Pro on.
      </p>
    </>
  );
}
