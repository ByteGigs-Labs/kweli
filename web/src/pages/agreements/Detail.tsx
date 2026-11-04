import { useState } from "react";
import { Link, useParams } from "react-router";
import { ProofChain, type ChainLink } from "../../components/ProofChain";
import { StatusChip } from "../../components/StatusChip";
import { UploadDeliverable } from "../../components/UploadDeliverable";
import {
  createInvoice,
  errorMessage,
  getAgreement,
  getInvoice,
  listDocuments,
  openDocument,
  sendAgreement,
  sendInvoice,
} from "../../lib/api";
import { shortDate } from "../../lib/dates";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import type { AcceptLink, Agreement, Invoice, StoredDocument } from "../../types";

function chainFor(
  agreement: Agreement,
  invoice: Invoice | undefined,
  documents: StoredDocument[] | undefined,
): ChainLink[] {
  const accepted = agreement.status === "accepted";
  const sent = invoice && invoice.status !== "draft";
  const paid = invoice && ["paid", "partially_paid"].includes(invoice.status);
  const delivered = documents?.find((document) => document.kind === "deliverable");
  return [
    {
      name: "Agreement",
      detail: accepted ? `Accepted ${shortDate(agreement.accepted_at)}` : "Not accepted yet",
      state: accepted ? "proven" : "missing",
    },
    {
      name: "Invoice",
      detail: sent ? `Sent ${shortDate(invoice.sent_at)}` : invoice ? "Draft, not sent" : "Not created",
      state: sent ? "proven" : "missing",
    },
    {
      name: "Payment",
      detail: paid ? (invoice.status === "paid" ? "Paid" : "Part paid") : "Not paid yet",
      state: paid ? "proven" : "missing",
    },
    {
      name: "Deliverable",
      detail: delivered ? "On file" : "Not uploaded",
      state: delivered ? "proven" : "missing",
    },
  ];
}

function AcceptancePanel({ agreement, onLink }: { agreement: Agreement; onLink: () => void }) {
  const [link, setLink] = useState<AcceptLink | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const issue = async () => {
    setBusy(true);
    setFailed(null);
    try {
      setLink(await sendAgreement(agreement.id));
      setCopied(false);
      onLink();
    } catch (failure) {
      setFailed(errorMessage(failure, "The link couldn't be created. Try again."));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!link) return;
    await navigator.clipboard?.writeText(link.url);
    setCopied(true);
  };

  return (
    <section className="panel" aria-labelledby="accept-title">
      <h2 id="accept-title">Get {agreement.client.name}'s acceptance</h2>
      <p className="muted">
        Send the client a link to read and accept this agreement. You can invoice once they accept.
      </p>
      {link ? (
        <div className="stack">
          <div className="link-box">
            <label className="visually-hidden" htmlFor="accept-url">
              Acceptance link
            </label>
            <input id="accept-url" readOnly value={link.url} onFocus={(event) => event.target.select()} />
            <button type="button" className="button" onClick={copy}>
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
          <p className="muted">
            Expires {shortDate(link.expires_at)}. Anyone with this link can accept, so send it only to{" "}
            {agreement.client.email}. Creating a new link turns this one off.
          </p>
        </div>
      ) : (
        <button type="button" className="button" onClick={issue} disabled={busy}>
          {busy ? "Creating…" : agreement.status === "sent" ? "Create a new link" : "Create acceptance link"}
        </button>
      )}
      {failed && (
        <p className="alert" role="alert">
          {failed}
        </p>
      )}
    </section>
  );
}

function InvoicePanel({
  agreement,
  invoice,
  onChange,
}: {
  agreement: Agreement;
  invoice: Invoice | undefined;
  onChange: (invoice: Invoice) => void;
}) {
  const [dueDate, setDueDate] = useState(agreement.due_date ?? "");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const act = async (action: () => Promise<Invoice>, fallback: string) => {
    setBusy(true);
    setFailed(null);
    try {
      onChange(await action());
    } catch (failure) {
      setFailed(errorMessage(failure, fallback));
    } finally {
      setBusy(false);
    }
  };

  const amount = formatMoney(agreement.amount_minor, agreement.currency);

  if (!invoice) {
    return (
      <section className="panel" aria-labelledby="invoice-title">
        <h2 id="invoice-title">Invoice {agreement.client.name}</h2>
        <p className="muted">
          Kweli creates a PayPal invoice for {amount}, linked to this agreement. It stays a draft until
          you send it.
        </p>
        <div className="field" style={{ marginBottom: 16 }}>
          <label htmlFor="invoice-due">Payment due</label>
          <input id="invoice-due" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} />
        </div>
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => act(() => createInvoice(agreement.id, dueDate || null), "The PayPal draft couldn't be created.")}
        >
          {busy ? "Creating…" : "Create PayPal draft"}
        </button>
        {failed && (
          <p className="alert" role="alert" style={{ marginTop: 16 }}>
            {failed}
          </p>
        )}
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="invoice-title">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
        <h2 id="invoice-title" style={{ margin: 0 }}>
          {invoice.status === "draft" ? "Check and send the invoice" : "Invoice sent"}
        </h2>
        <StatusChip status={invoice.status} />
      </div>
      <dl className="facts" style={{ marginBottom: 16 }}>
        <dt>To</dt>
        <dd>{agreement.client.email}</dd>
        <dt>Amount</dt>
        <dd>{formatMoney(invoice.amount_minor, invoice.currency)}</dd>
        <dt>Due</dt>
        <dd>{shortDate(invoice.due_date) || "On receipt"}</dd>
        <dt>PayPal number</dt>
        <dd>{invoice.number}</dd>
      </dl>
      {invoice.status === "draft" ? (
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={() => act(() => sendInvoice(invoice.id), "PayPal didn't send the invoice. Try again.")}
        >
          {busy ? "Sending…" : `Send to ${agreement.client.email} via PayPal`}
        </button>
      ) : (
        <p className="muted">
          PayPal emailed the invoice on {shortDate(invoice.sent_at)}.{" "}
          {invoice.payer_view_url && (
            <a href={invoice.payer_view_url} target="_blank" rel="noreferrer noopener">
              Open the invoice your client sees
            </a>
          )}
        </p>
      )}
      {failed && (
        <p className="alert" role="alert" style={{ marginTop: 16 }}>
          {failed}
        </p>
      )}
    </section>
  );
}

export function AgreementDetailPage() {
  const { id = "" } = useParams();
  const agreement = useAsync(() => getAgreement(id), [id]);
  const invoiceId = agreement.data?.invoice_id;
  const invoice = useAsync(
    () => (invoiceId ? getInvoice(invoiceId) : Promise.resolve(undefined)),
    [invoiceId],
  );
  const documents = useAsync(() => listDocuments(id), [id]);

  if (agreement.error) {
    return (
      <p className="alert" role="alert">
        This agreement couldn't be found. <Link to="/agreements">Back to agreements</Link>
      </p>
    );
  }
  const data = agreement.data;
  if (!data) return <p className="muted">Loading…</p>;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="muted" style={{ margin: 0 }}>
            <Link to="/agreements">Agreements</Link>
          </p>
          <h1>{data.title}</h1>
          <p>
            For {data.client.name}, {formatMoney(data.amount_minor, data.currency)}
            {data.due_date ? `, due ${shortDate(data.due_date)}` : ""}
          </p>
        </div>
        <StatusChip status={data.status} />
      </header>

      <div className="detail-layout">
        <div className="stack">
          <section className="panel" aria-label="Proof for this work">
            <ProofChain links={chainFor(data, invoice.data, documents.data)} />
          </section>
          <section className="panel" aria-labelledby="terms-title">
            <h2 id="terms-title">What the client accepts</h2>
            <ol className="terms">
              {data.terms?.map((term) => (
                <li key={term}>{term}</li>
              ))}
            </ol>
            <h2 style={{ marginTop: 24 }}>Deliverables</h2>
            <ul className="terms">
              {data.deliverables.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        </div>
        <div className="stack">
          <section className="panel" aria-labelledby="work-title">
            <h2 id="work-title">Delivered work</h2>
            {documents.data && documents.data.length > 0 ? (
              <ul className="file-list" style={{ marginBottom: 16 }}>
                {documents.data.map((document) => (
                  <li key={document.id}>
                    <button type="button" onClick={() => openDocument(document.id)}>
                      {document.filename}
                    </button>{" "}
                    <span className="muted">({Math.max(1, Math.round(document.size / 1024))} KB)</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                Upload the final files when you deliver. They prove the payment was for real work.
              </p>
            )}
            <UploadDeliverable agreementId={data.id} onUploaded={() => documents.reload()} />
          </section>
          {data.status === "accepted" ? (
            <InvoicePanel
              agreement={data}
              invoice={invoice.data}
              onChange={(next) => {
                invoice.setData(next);
                if (!data.invoice_id) agreement.setData({ ...data, invoice_id: next.id });
              }}
            />
          ) : (
            <AcceptancePanel
              agreement={data}
              onLink={() => agreement.setData({ ...data, status: "sent" })}
            />
          )}
        </div>
      </div>
    </>
  );
}
