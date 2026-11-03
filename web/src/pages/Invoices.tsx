import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { useNavigate } from "react-router";
import { StatusChip } from "../components/StatusChip";
import { listInvoices } from "../lib/api";
import { shortDate } from "../lib/dates";
import { kweliGridTheme } from "../lib/grid";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";
import type { Invoice } from "../types";

function NoInvoices() {
  return (
    <div className="empty" role="status">
      <h2>No invoices yet</h2>
      <p>Invoices start from an accepted agreement, so every one is linked to what the client agreed.</p>
    </div>
  );
}

export function InvoicesPage() {
  const navigate = useNavigate();
  const { data, error } = useAsync(listInvoices, []);
  const columns = useMemo<ColDef<Invoice>[]>(
    () => [
      { field: "number", headerName: "Number", width: 120 },
      { field: "description", headerName: "Work", flex: 1, minWidth: 180 },
      {
        field: "amount_minor",
        headerName: "Amount",
        width: 130,
        type: "rightAligned",
        valueFormatter: ({ value, data }) => (data ? formatMoney(value, data.currency) : ""),
      },
      { field: "due_date", headerName: "Due", width: 130, valueFormatter: ({ value }) => shortDate(value) },
      { field: "sent_at", headerName: "Sent", width: 130, valueFormatter: ({ value }) => shortDate(value) },
      {
        field: "status",
        headerName: "Status",
        width: 130,
        cellRenderer: ({ value }: ICellRendererParams<Invoice>) => <StatusChip status={value} />,
      },
    ],
    [],
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Invoices</h1>
          <p>PayPal invoices, each tied to the agreement it bills for.</p>
        </div>
      </header>
      {error ? (
        <p className="alert" role="alert">
          Invoices couldn't load. Refresh the page to try again.
        </p>
      ) : (
        <div className="grid-frame grid-frame-short clickable-rows">
          <AgGridReact<Invoice>
            theme={kweliGridTheme}
            rowData={data}
            loading={data === undefined}
            columnDefs={columns}
            defaultColDef={{ resizable: true, suppressMovable: true }}
            noRowsOverlayComponent={NoInvoices}
            getRowId={({ data }) => data.id}
            onRowClicked={({ data }) => data?.agreement_id && navigate(`/agreements/${data.agreement_id}`)}
          />
        </div>
      )}
    </>
  );
}
