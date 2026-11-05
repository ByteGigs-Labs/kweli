import type {
  AcceptLink,
  AgentAction,
  AgentReply,
  ChatMessage,
  Agreement,
  Billing,
  Dispute,
  DisputeSummary,
  AgreementInput,
  EngagementDraft,
  Invoice,
  LedgerDetail,
  LetterProblem,
  LedgerRow,
  Pack,
  PackSummary,
  PortalAgreement,
  Readiness,
  StoredDocument,
} from "../types";
import { http } from "./http";

export const readThread = async (thread: string) =>
  (await http.post<EngagementDraft>("/v1/agreements/extract", { thread })).data;

export const listAgreements = async () =>
  (await http.get<Agreement[]>("/v1/agreements", { params: { _start: 0, _end: 100 } })).data;

export const createAgreement = async (input: AgreementInput) =>
  (await http.post<Agreement>("/v1/agreements", input)).data;

export const getAgreement = async (id: string) =>
  (await http.get<Agreement>(`/v1/agreements/${encodeURIComponent(id)}`)).data;

export const sendAgreement = async (id: string) =>
  (await http.post<AcceptLink>(`/v1/agreements/${encodeURIComponent(id)}/send`)).data;

export const listInvoices = async () =>
  (await http.get<Invoice[]>("/v1/invoices", { params: { _start: 0, _end: 100 } })).data;

export const getInvoice = async (id: string) =>
  (await http.get<Invoice>(`/v1/invoices/${encodeURIComponent(id)}`)).data;

export const createInvoice = async (agreementId: string, dueDate: string | null) =>
  (await http.post<Invoice>("/v1/invoices", { agreement_id: agreementId, due_date: dueDate })).data;

export const sendInvoice = async (id: string) =>
  (await http.post<Invoice>(`/v1/invoices/${encodeURIComponent(id)}/send`)).data;

export const viewPortal = async (token: string) =>
  (await http.get<PortalAgreement>(`/v1/portal/agreements/${encodeURIComponent(token)}`)).data;

export const acceptPortal = async (token: string) =>
  (
    await http.post<PortalAgreement>(`/v1/portal/agreements/${encodeURIComponent(token)}/accept`, {
      accept: true,
    })
  ).data;

export const listLedger = async () =>
  (await http.get<LedgerRow[]>("/v1/ledger", { params: { _start: 0, _end: 100 } })).data;

export const getLedgerEntry = async (id: string) =>
  (await http.get<LedgerDetail>(`/v1/ledger/${encodeURIComponent(id)}`)).data;

export const listDocuments = async (agreementId: string) =>
  (await http.get<StoredDocument[]>("/v1/documents", { params: { agreement_id: agreementId } })).data;

export type ProofDocumentKind = "deliverable" | "payer_confirmation";

export const uploadProof = async (agreementId: string, file: File, kind: ProofDocumentKind) => {
  const body = new FormData();
  body.append("file", file);
  body.append("kind", kind);
  body.append("agreement_id", agreementId);
  return (await http.post<StoredDocument>("/v1/documents", body)).data;
};

export const uploadDeliverable = (agreementId: string, file: File) =>
  uploadProof(agreementId, file, "deliverable");

export const getReadiness = async () => (await http.get<Readiness>("/v1/readiness")).data;

export const linkPaymentAgreement = async (paymentId: string, agreementId: string | null) =>
  (
    await http.post<LedgerDetail>(`/v1/ledger/${encodeURIComponent(paymentId)}/agreement`, {
      agreement_id: agreementId,
    })
  ).data;

export const openDocument = async (id: string) => {
  const { url } = (await http.get<{ url: string }>(`/v1/documents/${encodeURIComponent(id)}/url`)).data;
  window.location.assign(url);
};

export const askAgent = async (messages: ChatMessage[]) =>
  (await http.post<AgentReply>("/v1/agent/messages", { messages }, { timeout: 90000 })).data;

export const approveAction = async (id: string, token: string) =>
  (await http.post<AgentAction>(`/v1/agent/actions/${encodeURIComponent(id)}/approve`, { token }, { timeout: 60000 }))
    .data;

export const rejectAction = async (id: string) =>
  (await http.post<AgentAction>(`/v1/agent/actions/${encodeURIComponent(id)}/reject`)).data;

export const createPack = async (periodStart: string, periodEnd: string) =>
  (
    await http.post<Pack>(
      "/v1/packs",
      { period_start: periodStart, period_end: periodEnd },
      { timeout: 120000 },
    )
  ).data;

export const listPacks = async () => (await http.get<PackSummary[]>("/v1/packs")).data;

export const getPack = async (id: string) =>
  (await http.get<Pack>(`/v1/packs/${encodeURIComponent(id)}`)).data;

export const editPackLetter = async (id: string, letter: string) =>
  (await http.put<Pack>(`/v1/packs/${encodeURIComponent(id)}/letter`, { letter }, { timeout: 120000 }))
    .data;

const disputePath = (id: string, action = "") =>
  `/v1/disputes/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;

export const listDisputes = async () => (await http.get<DisputeSummary[]>("/v1/disputes")).data;

export const getDispute = async (id: string) => (await http.get<Dispute>(disputePath(id))).data;

export const prepareDispute = async (id: string) =>
  (await http.post<Dispute>(disputePath(id, "prepare"), undefined, { timeout: 90000 })).data;

export const editDisputeResponse = async (id: string, text: string) =>
  (await http.put<Dispute>(disputePath(id, "response"), { text })).data;

export const approveDispute = async (id: string) =>
  (await http.post<Dispute>(disputePath(id, "approval"))).data;

export const submitDispute = async (id: string, token: string) =>
  (await http.post<Dispute>(disputePath(id, "submit"), { token }, { timeout: 120000 })).data;

export const refreshDispute = async (id: string) =>
  (await http.post<Dispute>(disputePath(id, "refresh"))).data;

export const sandboxDispute = async (
  id: string,
  action: "require_evidence" | "seller_favor" | "buyer_favor",
) => (await http.post<Dispute>(disputePath(id, "sandbox"), { action }, { timeout: 60000 })).data;

export const getBilling = async () => (await http.get<Billing>("/v1/billing")).data;

export const startCheckout = async () =>
  (await http.post<{ approve_url: string }>("/v1/billing/checkout", undefined, { timeout: 30000 })).data;

export const confirmBilling = async (subscriptionId: string) =>
  (await http.post<Billing>("/v1/billing/confirm", { subscription_id: subscriptionId }, { timeout: 30000 }))
    .data;

export const cancelBilling = async () =>
  (await http.post<Billing>("/v1/billing/cancel", undefined, { timeout: 30000 })).data;

export const needsPro = (failure: unknown) =>
  (failure as { response?: { status?: number } })?.response?.status === 402;

export const errorMessage = (failure: unknown, fallback: string) => {
  const data = (failure as { response?: { data?: { error?: { message?: string } } } }).response?.data;
  return data?.error?.message ?? fallback;
};

export const errorProblems = (failure: unknown) => {
  const data = (failure as { response?: { data?: { error?: { problems?: LetterProblem[] } } } }).response
    ?.data;
  return data?.error?.problems ?? [];
};
