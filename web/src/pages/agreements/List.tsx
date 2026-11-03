import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router";
import { StatusChip } from "../../components/StatusChip";
import { listAgreements } from "../../lib/api";
import { shortDate } from "../../lib/dates";
import { kweliGridTheme } from "../../lib/grid";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import type { Agreement } from "../../types";

function NoAgreements() {
  return (
    <div className="empty" role="status">
      <h2>No agreements yet</h2>
      <p>Paste a conversation with a client and Kweli turns it into an agreement they can accept.</p>
    </div>
  );
}

export function AgreementsPage() {
  const navigate = useNavigate();
  const { data, error } = useAsync(listAgreements, []);
  const columns = useMemo<ColDef<Agreement>[]>(
    () => [
      { field: "title", headerName: "Work", flex: 1.4, minWidth: 180 },
      { headerName: "Client", flex: 1, minWidth: 140, valueGetter: ({ data }) => data?.client.name },
      {
        field: "amount_minor",
        headerName: "Fee",
        width: 130,
        type: "rightAligned",
        valueFormatter: ({ value, data }) => (data ? formatMoney(value, data.currency) : ""),
      },
      { field: "due_date", headerName: "Due", width: 130, valueFormatter: ({ value }) => shortDate(value) },
      {
        field: "status",
        headerName: "Status",
        width: 130,
        cellRenderer: ({ value }: ICellRendererParams<Agreement>) => <StatusChip status={value} />,
      },
    ],
    [],
  );

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Agreements</h1>
          <p>What you and each client agreed, accepted by them before you invoice.</p>
        </div>
        <Link className="button" to="/agreements/new">
          New agreement
        </Link>
      </header>
      {error ? (
        <p className="alert" role="alert">
          Agreements couldn't load. Refresh the page to try again.
        </p>
      ) : (
        <div className="grid-frame grid-frame-short clickable-rows">
          <AgGridReact<Agreement>
            theme={kweliGridTheme}
            rowData={data}
            loading={data === undefined}
            columnDefs={columns}
            defaultColDef={{ resizable: true, suppressMovable: true }}
            noRowsOverlayComponent={NoAgreements}
            getRowId={({ data }) => data.id}
            onRowClicked={({ data }) => data && navigate(`/agreements/${data.id}`)}
          />
        </div>
      )}
    </>
  );
}
