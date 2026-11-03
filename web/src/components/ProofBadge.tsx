import type { ProofStatus } from "../types";

const LABEL: Record<ProofStatus, string> = { pass: "On file", warn: "Needs attention", fail: "Missing" };

export function ProofBadge({ status }: { status: ProofStatus | undefined }) {
  if (!status) return <span className="badge badge-none">—</span>;
  return (
    <span className={`badge badge-${status}`} title={LABEL[status]}>
      <span className="visually-hidden">{LABEL[status]}</span>
      <span aria-hidden="true">{status === "pass" ? "✓" : status === "warn" ? "!" : "×"}</span>
    </span>
  );
}
