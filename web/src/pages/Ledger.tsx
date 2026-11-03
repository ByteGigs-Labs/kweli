import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { ProofBadge } from "../components/ProofBadge";
import { kweliGridTheme } from "../lib/grid";
import { formatMoney } from "../lib/money";
import type { LedgerRow, RuleId } from "../types";

const RULES: { id: RuleId; name: string; question: string }[] = [
  { id: "P1", name: "Invoiced", question: "Is the payment linked to a Kweli invoice?" },
  { id: "P2", name: "Matches", question: "Does the amount and currency match the invoice?" },
  { id: "P3", name: "Payer", question: "Did the client on the agreement pay?" },
  { id: "P4", name: "Agreed", question: "Is there an accepted agreement?" },
  { id: "P5", name: "Work", question: "Is the delivered work attached?" },
  { id: "P6", name: "Type", question: "Was it paid as a business payment?" },
  { id: "P7", name: "Volume", question: "Is the amount usual for this account?" },
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

export function LedgerPage({ rows = [] }: { rows?: LedgerRow[] }) {
  const columns = useMemo<ColDef<LedgerRow>[]>(
    () => [
      {
        field: "received_at",
        headerName: "Received",
        width: 130,
        valueFormatter: ({ value }) =>
          value ? new Date(value).toLocaleDateString("en-KE", { day: "numeric", month: "short" }) : "",
        sort: "desc",
      },
      { field: "client", headerName: "Client", flex: 1, minWidth: 140 },
      {
        field: "amount_minor",
        headerName: "Amount",
        width: 120,
        type: "rightAligned",
        cellClass: "tabular",
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

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Proof ledger</h1>
          <p>Every payment you receive, with the proof behind it.</p>
        </div>
      </header>
      <div className="grid-frame">
        <AgGridReact<LedgerRow>
          theme={kweliGridTheme}
          rowData={rows}
          columnDefs={columns}
          defaultColDef={{ resizable: true, suppressMovable: true }}
          noRowsOverlayComponent={EmptyLedger}
          getRowId={({ data }) => data.id}
          animateRows={false}
        />
      </div>
    </>
  );
}
