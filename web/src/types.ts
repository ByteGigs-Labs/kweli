export interface Identity {
  id: string;
  email: string;
  name: string;
  plan: "free" | "pro";
}

export type ProofStatus = "pass" | "warn" | "fail" | "pending";
export type RuleId = "P1" | "P2" | "P3" | "P4" | "P5" | "P6" | "P7";

export interface LedgerRow {
  id: string;
  received_at: string;
  client: string;
  amount_minor: number;
  currency: string;
  rules: Partial<Record<RuleId, ProofStatus>>;
  status: ProofStatus;
}

export interface Client {
  id: string;
  name: string;
  email: string;
  country: string | null;
  created_at: string;
}

export type AgreementStatus = "draft" | "sent" | "accepted" | "expired";

export interface Agreement {
  id: string;
  client: Client;
  title: string;
  scope: string;
  deliverables: string[];
  amount: string;
  amount_minor: number;
  currency: string;
  due_date: string | null;
  status: AgreementStatus;
  sent_at: string | null;
  accepted_at: string | null;
  created_at: string;
  invoice_id: string | null;
  terms?: string[];
}

export interface AgreementInput {
  client: { name: string; email: string; country?: string | null };
  title: string;
  scope: string;
  deliverables: string[];
  amount: string;
  currency: string;
  due_date: string | null;
}

export interface EngagementDraft {
  client_name: string | null;
  client_email: string | null;
  title: string | null;
  scope: string | null;
  deliverables: string[];
  amount: string | null;
  currency: string | null;
  due_date: string | null;
  missing: string[];
  notes: string[];
}

export interface AcceptLink {
  url: string;
  expires_at: string;
}

export type InvoiceStatus = "draft" | "sent" | "paid" | "partially_paid" | "cancelled" | "refunded";

export interface Invoice {
  id: string;
  agreement_id: string | null;
  client_id: string;
  paypal_invoice_id: string | null;
  number: string;
  description: string;
  amount_minor: number;
  currency: string;
  due_date: string | null;
  status: InvoiceStatus;
  payer_view_url: string | null;
  sent_at: string | null;
  created_at: string;
}

export interface PortalAgreement {
  freelancer: string;
  client: string;
  title: string;
  deliverables: string[];
  amount: string;
  currency: string;
  due_date: string | null;
  terms: string[];
  status: AgreementStatus;
  accepted_at: string | null;
}

export interface LedgerFlag {
  rule: RuleId;
  status: ProofStatus;
  explanation: string;
  fix: string | null;
}

export interface LedgerDetail extends LedgerRow {
  payer: string | null;
  payment_type: string;
  flags: LedgerFlag[];
  chain: { name: string; proven: boolean; detail: string }[];
  agreement_id: string | null;
  invoice_number: string | null;
  linked_by: "invoice" | "hand" | null;
  payer_confirmation: string | null;
}

export type ReadinessBand = "ready" | "nearly" | "at_risk" | "no_payments";

export interface FixStep {
  rule: RuleId;
  status: ProofStatus;
  problem: string;
  fix: string;
}

export interface FixItem {
  payment_id: string;
  agreement_id: string | null;
  client: string;
  amount_minor: number;
  currency: string;
  received_at: string;
  status: ProofStatus;
  points: number;
  steps: FixStep[];
}

export interface ClientSummary {
  client: string;
  payments: number;
  totals: { currency: string; amount_minor: number }[];
  statuses: Record<ProofStatus, number>;
  score: number | null;
}

export interface Readiness {
  score: number | null;
  band: ReadinessBand;
  thresholds: { ready: number; nearly: number };
  payments: number;
  statuses: Record<ProofStatus, number>;
  checks: Record<ProofStatus, number>;
  large_payments: number;
  fix_total: number;
  fix_next: FixItem[];
  clients: ClientSummary[];
}

export interface StoredDocument {
  id: string;
  agreement_id: string | null;
  kind: string;
  filename: string;
  mime: string;
  size: number;
  sha256: string;
}

export interface AgentStep {
  tool: string;
  label: string;
  ok: boolean;
}

export type AgentActionStatus = "proposed" | "approved" | "rejected" | "executed" | "failed";

export interface AgentAction {
  id: string;
  kind: string;
  title: string;
  details: { label: string; value: string }[];
  status: AgentActionStatus;
  expires_at: string;
  token: string | null;
  result: { message?: string; link?: string | null } | null;
}

export interface AgentReply {
  reply: string;
  steps: AgentStep[];
  actions: AgentAction[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export type LetterSource = "ai" | "standard" | "edited";

export interface LetterProblem {
  code: string;
  message: string;
  excerpt: string;
}

export interface PackSummary {
  id: string;
  period_start: string;
  period_end: string;
  letter_source: LetterSource;
  payments: number;
  statuses: Partial<Record<ProofStatus, number>>;
  totals: { currency: string; amount_minor: number }[];
  created_at: string;
  updated_at: string | null;
  pdf_document_id: string | null;
  zip_document_id: string | null;
}

export interface Pack extends PackSummary {
  letter: string;
  summary: {
    payments: number;
    clients: number;
    documents: number;
    attached: number;
    left_out: string[];
    ai_rejected: LetterProblem[];
    letter_attempts: number;
    pdf_sha256: string;
    zip_sha256: string;
    audit_head: string;
  };
}
