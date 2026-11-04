import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo, useState } from "react";
import { LedgerDrawer } from "../components/LedgerDrawer";
import { ProofBadge } from "../components/ProofBadge";
import { listLedger } from "../lib/api";
import { kweliGridTheme } from "../lib/grid";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";
import type { LedgerRow, ProofStatus, RuleId } from "../types";

const RULES: { id: RuleId; name: string; question: string }[] = [
  { id: "P1", name: "Invoiced", question: "Is the payment linked to a Kweli invoice?" },
  { id: "P2", name: "Matches", question: "Does the amount and currency match the invoice?" },
  { id: "P3", name: "Payer", question: "Did the client on the agreement pay?" },
  { id: "P4", name: "Agreed", question: "Is there an accepted agreement?" },
  { id: "P5", name: "Work", question: "Is the delivered work attached?" },
  { id: "P6", name: "Type", question: "Was it paid as a business payment?" },
  { id: "P7", name: "Volume", question: "Is the amount usual for this account?" },
];

const SUMMARY: { status: ProofStatus; label: string }[] = [
  { status: "pass", label: "fully proven" },
  { status: "warn", label: "need attention" },
  { status: "fail", label: "missing proof" },
  { status: "pending", label: "being checked" },
];

function EmptyLedger() {
  return (
    <div className="empty" role="status">
      <h2>No payments yet</h2>
      <p>
        Payments appear here as soon as a client pays a Kweli invoice. Each one shows which proofs
        are on file and which are missing.
      </p>
    </div>
  );
}

export function LedgerPage() {
  const loaded = useAsync(listLedger, []);
  const rows = loaded.data;
  const [open, setOpen] = useState<string | null>(null);

  const columns = useMemo<ColDef<LedgerRow>[]>(
    () => [
      {
        field: "status",
        headerName: "Proof",
        width: 96,
        cellRenderer: ({ value }: ICellRendererParams<LedgerRow>) => <ProofBadge status={value} />,
        comparator: (a: ProofStatus, b: ProofStatus) =>
          ["fail", "warn", "pending", "pass"].indexOf(a) - ["fail", "warn", "pending", "pass"].indexOf(b),
      },
      {
        field: "received_at",
        headerName: "Received",
        width: 120,
        valueFormatter: ({ value }) =>
          value ? new Date(value).toLocaleDateString("en-KE", { day: "numeric", month: "short" }) : "",
        sort: "desc",
      },
      { field: "client", headerName: "Client", flex: 1, minWidth: 150 },
      {
        field: "amount_minor",
        headerName: "Amount",
        width: 130,
        type: "rightAligned",
        valueFormatter: ({ value, data }) => (data ? formatMoney(value, data.currency) : ""),
      },
      ...RULES.map(
        (rule): ColDef<LedgerRow> => ({
          colId: rule.id,
          headerName: rule.name,
          headerTooltip: `${rule.id}: ${rule.question}`,
          width: 92,
          sortable: false,
          valueGetter: ({ data }) => data?.rules[rule.id],
          cellRenderer: ({ value }: ICellRendererParams<LedgerRow>) => <ProofBadge status={value} />,
        }),
      ),
    ],
    [],
  );

  const counts = useMemo(() => {
    const tally: Record<ProofStatus, number> = { pass: 0, warn: 0, fail: 0, pending: 0 };
    rows?.forEach((row) => (tally[row.status] += 1));
    return tally;
  }, [rows]);

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Proof ledger</h1>
          <p>Every payment you receive, with the proof behind it. Select a payment to see what to fix.</p>
        </div>
      </header>
      {rows && rows.length > 0 && (
        <ul className="ledger-summary" aria-label="Summary">
          {SUMMARY.filter((item) => counts[item.status] > 0).map((item) => (
            <li key={item.status}>
              <ProofBadge status={item.status} />
              <span>
                <strong>{counts[item.status]}</strong> {item.label}
              </span>
            </li>
          ))}
        </ul>
      )}
      {loaded.error !== undefined ? (
        <p className="alert" role="alert">
          The ledger couldn't load. Refresh the page to try again.
        </p>
      ) : (
        <div className="grid-frame clickable-rows">
          <AgGridReact<LedgerRow>
            theme={kweliGridTheme}
            rowData={rows}
            loading={rows === undefined}
            columnDefs={columns}
            defaultColDef={{ resizable: true, suppressMovable: true }}
            noRowsOverlayComponent={EmptyLedger}
            getRowId={({ data }) => data.id}
            animateRows={false}
            onRowClicked={({ data }) => data && setOpen(data.id)}
            onCellKeyDown={(event) => {
              const key = (event.event as KeyboardEvent | undefined)?.key;
              if (key === "Enter" && event.data) setOpen(event.data.id);
            }}
          />
        </div>
      )}
      {open && (
        <LedgerDrawer paymentId={open} onClose={() => setOpen(null)} onChanged={() => loaded.reload()} />
      )}
    </>
  );
}
