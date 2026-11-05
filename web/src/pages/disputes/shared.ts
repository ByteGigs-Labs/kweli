import type { DisputeSummary } from "../../types";

export const STATUS_LABEL: Record<string, string> = {
  OPEN: "Open",
  WAITING_FOR_SELLER_RESPONSE: "Waiting for your response",
  WAITING_FOR_BUYER_RESPONSE: "Waiting for the client",
  UNDER_REVIEW: "PayPal is reviewing",
  RESOLVED: "Resolved",
  OTHER: "Open",
};

export const OUTCOME_LABEL: Record<string, string> = {
  RESOLVED_SELLER_FAVOUR: "Decided in your favour",
  RESOLVED_BUYER_FAVOUR: "Decided in the client's favour",
  RESOLVED_WITH_PAYOUT: "Resolved with a PayPal payout",
  CANCELED_BY_BUYER: "Cancelled by the client",
  ACCEPTED: "Claim accepted",
  DENIED: "Claim denied",
  NONE: "Closed without a decision",
};

export function tone(dispute: DisputeSummary): "pass" | "warn" | "fail" | "pending" {
  if (dispute.outcome === "RESOLVED_SELLER_FAVOUR" || dispute.outcome === "CANCELED_BY_BUYER") return "pass";
  if (dispute.status === "RESOLVED") return dispute.outcome === "RESOLVED_BUYER_FAVOUR" ? "fail" : "pending";
  if (dispute.status === "WAITING_FOR_SELLER_RESPONSE" && !dispute.submitted_at) return "fail";
  return "pending";
}

export function dueText(value: string | null, now = new Date()) {
  if (!value) return null;
  const due = new Date(value);
  const days = Math.ceil((due.getTime() - now.getTime()) / 86_400_000);
  const date = due.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  if (days < 0) return `Response was due ${date}`;
  if (days === 0) return `Respond by today, ${date}`;
  return `Respond by ${date} (${days} day${days === 1 ? "" : "s"} left)`;
}
