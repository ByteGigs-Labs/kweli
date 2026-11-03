const LABEL: Record<string, string> = {
  draft: "Draft",
  sent: "Sent",
  accepted: "Accepted",
  expired: "Expired",
  paid: "Paid",
  partially_paid: "Part paid",
  cancelled: "Cancelled",
  refunded: "Refunded",
};

const TONE: Record<string, "quiet" | "wait" | "done" | "stop"> = {
  draft: "quiet",
  sent: "wait",
  accepted: "done",
  paid: "done",
  partially_paid: "wait",
  expired: "stop",
  cancelled: "stop",
  refunded: "stop",
};

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip chip-${TONE[status] ?? "quiet"}`}>{LABEL[status] ?? status}</span>;
}
