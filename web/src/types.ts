export interface Identity {
  id: string;
  email: string;
  name: string;
  plan: "free" | "pro";
}

export type ProofStatus = "pass" | "warn" | "fail";
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
