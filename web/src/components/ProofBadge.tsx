import type { ProofStatus } from "../types";

export const PROOF_LABEL: Record<ProofStatus, string> = {
  pass: "On file",
  warn: "Needs attention",
  fail: "Missing",
  pending: "Checking",
};

const ICON: Record<ProofStatus, React.ReactNode> = {
  pass: <path d="M5 10.5l3.2 3.2L15 7" />,
  warn: (
    <>
      <path d="M10 5.5v5.5" />
      <path d="M10 14.5v0.01" />
    </>
  ),
  fail: <path d="M6.5 6.5l7 7M13.5 6.5l-7 7" />,
  pending: <path d="M6 10h0.01M10 10h0.01M14 10h0.01" />,
};

export function ProofBadge({ status }: { status: ProofStatus | undefined }) {
  if (!status) return <span className="badge badge-none">—</span>;
  return (
    <span className={`badge badge-${status}`} title={PROOF_LABEL[status]}>
      <span className="visually-hidden">{PROOF_LABEL[status]}</span>
      <svg
        width="16"
        height="16"
        viewBox="0 0 20 20"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        strokeWidth={status === "pending" ? 3 : 2.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {ICON[status]}
      </svg>
    </span>
  );
}
