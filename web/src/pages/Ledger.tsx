import type { ColDef, GridApi, ICellRendererParams, IRowNode, ProcessCellForExportParams } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { LedgerDrawer } from "../components/LedgerDrawer";
import { PROOF_LABEL, ProofBadge } from "../components/ProofBadge";
import { bandFor, ScoreMeter } from "../components/ScoreMeter";
import { getReadiness, listLedger } from "../lib/api";
import { kweliGridTheme } from "../lib/grid";
import { formatMoney } from "../lib/money";
import { useAsync } from "../lib/useAsync";
import type { ClientSummary, LedgerRow, ProofStatus, RuleId } from "../types";

export const RULES: { id: RuleId; name: string; question: string }[] = [
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

const WORST_FIRST: ProofStatus[] = ["fail", "warn", "pending", "pass"];
const STATUSES = new Set<string>(WORST_FIRST);

const shortDate = (value: string) =>
  new Date(value).toLocaleDateString("en-KE", { day: "numeric", month: "short" });

const toDecimal = (amountMinor: number, currency: string) =>
  formatMoney(amountMinor, currency).replace(/[^\d.,-]/g, "").replace(/,/g, "");

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

function NoMatches() {
  return (
    <div className="empty" role="status">
      <h2>No payments match</h2>
      <p>Clear the search or filters to see every payment.</p>
    </div>
  );
}

function exportCell({ column, value, node }: ProcessCellForExportParams<LedgerRow>) {
  const id = column.getColId();
  if (id === "amount_minor" && node?.data) return toDecimal(node.data.amount_minor, node.data.currency);
  if (id === "received_at" && typeof value === "string") return value.slice(0, 10);
  if (id === "status" || RULES.some((rule) => rule.id === id)) {
    return value ? PROOF_LABEL[value as ProofStatus] : "";
  }
  return value;
}

function ClientsView({ onPick }: { onPick: (client: string) => void }) {
  const loaded = useAsync(getReadiness, []);
  const columns = useMemo<ColDef<ClientSummary>[]>(
    () => [
      {
        field: "score",
        headerName: "Readiness",
        width: 140,
        sort: "asc",
        cellRenderer: ({ value, data }: ICellRendererParams<ClientSummary>) => {
          const score = (value as number | null) ?? null;
          const band = bandFor(score);
          return (
            <ScoreMeter
              score={score}
              band={band === "ready" && data?.statuses.fail ? "nearly" : band}
              size="small"
            />
          );
        },
      },
      { field: "client", headerName: "Client", flex: 1, minWidth: 140 },
      { field: "payments", headerName: "Payments", width: 110, type: "rightAligned" },
      {
        colId: "totals",
        headerName: "Received",
        width: 150,
        type: "rightAligned",
        sortable: false,
        valueGetter: ({ data }) =>
          data?.totals.map((total) => formatMoney(total.amount_minor, total.currency)).join(", "),
      },
      ...SUMMARY.map(
        (item): ColDef<ClientSummary> => ({
          colId: item.status,
          headerName: item.label.replace(/^\w/, (c) => c.toUpperCase()),
          width: 136,
          type: "rightAligned",
          valueGetter: ({ data }) => data?.statuses[item.status] ?? 0,
        }),
      ),
    ],
    [],
  );

  if (loaded.error !== undefined) {
    return (
      <p className="alert" role="alert">
        The client summary couldn't load. Refresh the page to try again.
      </p>
    );
  }
  return (
    <div className="grid-frame clickable-rows">
      <AgGridReact<ClientSummary>
        theme={kweliGridTheme}
        rowData={loaded.data?.clients}
        loading={loaded.data === undefined}
        columnDefs={columns}
        defaultColDef={{ resizable: true, suppressMovable: true }}
        noRowsOverlayComponent={EmptyLedger}
        getRowId={({ data }) => data.client}
        animateRows={false}
        onRowClicked={({ data }) => data && onPick(data.client)}
        onCellKeyDown={(event) => {
          const key = (event.event as KeyboardEvent | undefined)?.key;
          if (key === "Enter" && event.data) onPick(event.data.client);
        }}
      />
    </div>
  );
}

export function LedgerPage() {
  const loaded = useAsync(listLedger, []);
  const rows = loaded.data;
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const grid = useRef<GridApi<LedgerRow> | null>(null);

  const open = params.get("payment");
  const client = params.get("client");
  const rawStatus = params.get("status");
  const status = rawStatus && STATUSES.has(rawStatus) ? (rawStatus as ProofStatus) : null;
  const view = params.get("view") === "clients" ? "clients" : "payments";

  const update = useCallback(
    (changes: Record<string, string | null>) =>
      setParams(
        (current) => {
          const next = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null) next.delete(key);
            else next.set(key, value);
          }
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );

  const filters = useRef({ client, status });
  useEffect(() => {
    filters.current = { client, status };
    grid.current?.onFilterChanged();
  }, [client, status]);

  const columns = useMemo<ColDef<LedgerRow>[]>(
    () => [
      {
        field: "status",
        headerName: "Proof",
        width: 88,
        cellRenderer: ({ value }: ICellRendererParams<LedgerRow>) => <ProofBadge status={value} />,
        comparator: (a: ProofStatus, b: ProofStatus) => WORST_FIRST.indexOf(a) - WORST_FIRST.indexOf(b),
        getQuickFilterText: ({ value }) => (value ? PROOF_LABEL[value as ProofStatus] : ""),
      },
      {
        field: "received_at",
        headerName: "Received",
        width: 130,
        valueFormatter: ({ value }) => (value ? shortDate(value) : ""),
        getQuickFilterText: ({ value }) => (value ? shortDate(value) : ""),
        sort: "desc",
        filter: "agDateColumnFilter",
        filterValueGetter: ({ data }) => (data ? new Date(data.received_at) : null),
        filterParams: {
          comparator: (day: Date, value: Date | null) => {
            if (!value) return -1;
            const start = new Date(value.getFullYear(), value.getMonth(), value.getDate());
            return start < day ? -1 : start > day ? 1 : 0;
          },
        },
      },
      { field: "client", headerName: "Client", flex: 1, minWidth: 120, filter: "agTextColumnFilter" },
      {
        field: "amount_minor",
        headerName: "Amount",
        width: 140,
        type: "rightAligned",
        valueFormatter: ({ value, data }) => (data ? formatMoney(value, data.currency) : ""),
        getQuickFilterText: ({ data }) => (data ? formatMoney(data.amount_minor, data.currency) : ""),
        filter: "agNumberColumnFilter",
        filterValueGetter: ({ data }) => (data ? data.amount_minor / 100 : null),
      },
      { field: "currency", headerName: "Currency", hide: true },
      ...RULES.map(
        (rule): ColDef<LedgerRow> => ({
          colId: rule.id,
          headerName: rule.name,
          headerTooltip: `${rule.id}: ${rule.question}`,
          width: 90,
          sortable: false,
          valueGetter: ({ data }) => data?.rules[rule.id],
          cellRenderer: ({ value }: ICellRendererParams<LedgerRow>) => <ProofBadge status={value} />,
          getQuickFilterText: () => "",
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

  const exportCsv = () =>
    grid.current?.exportDataAsCsv({
      fileName: `kweli-proof-ledger-${new Date().toISOString().slice(0, 10)}.csv`,
      allColumns: true,
      processCellCallback: exportCell,
    });

  const filtered = Boolean(client || status || search);

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Proof ledger</h1>
          <p>Every payment you receive, with the proof behind it. Select a payment to see what to fix.</p>
        </div>
      </header>

      <div className="ledger-toolbar">
        <div className="segmented" role="group" aria-label="View">
          <button
            type="button"
            aria-pressed={view === "payments"}
            onClick={() => update({ view: null })}
          >
            Payments
          </button>
          <button
            type="button"
            aria-pressed={view === "clients"}
            onClick={() => update({ view: "clients", payment: null })}
          >
            By client
          </button>
        </div>
        {view === "payments" && (
          <>
            <label className="search">
              <span className="visually-hidden">Search payments</span>
              <input
                type="search"
                placeholder="Search client, amount or date"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="button button-quiet"
              onClick={exportCsv}
              disabled={!rows?.length}
            >
              Export CSV
            </button>
          </>
        )}
      </div>

      {view === "payments" && rows && rows.length > 0 && (
        <div className="ledger-filters">
          <ul className="ledger-summary" aria-label="Summary">
            {SUMMARY.filter((item) => counts[item.status] > 0).map((item) => (
              <li key={item.status}>
                <button
                  type="button"
                  className="summary-chip"
                  aria-pressed={status === item.status}
                  onClick={() => update({ status: status === item.status ? null : item.status })}
                >
                  <ProofBadge status={item.status} />
                  <span>
                    <strong>{counts[item.status]}</strong> {item.label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {client && (
            <button type="button" className="filter-chip" onClick={() => update({ client: null })}>
              Client: {client}
              <span aria-hidden="true">×</span>
              <span className="visually-hidden">(remove filter)</span>
            </button>
          )}
          {filtered && (
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setSearch("");
                update({ client: null, status: null });
              }}
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {view === "clients" ? (
        <ClientsView onPick={(name) => update({ view: null, client: name, status: null })} />
      ) : loaded.error !== undefined ? (
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
            noRowsOverlayComponent={rows && rows.length > 0 ? NoMatches : EmptyLedger}
            getRowId={({ data }) => data.id}
            animateRows={false}
            quickFilterText={search}
            cacheQuickFilter
            isExternalFilterPresent={() => Boolean(filters.current.client || filters.current.status)}
            doesExternalFilterPass={(node: IRowNode<LedgerRow>) =>
              (!filters.current.client || node.data?.client === filters.current.client) &&
              (!filters.current.status || node.data?.status === filters.current.status)
            }
            onGridReady={({ api }) => {
              grid.current = api;
              api.onFilterChanged();
            }}
            onRowClicked={({ data }) => data && update({ payment: data.id })}
            onCellKeyDown={(event) => {
              const key = (event.event as KeyboardEvent | undefined)?.key;
              if (key === "Enter" && event.data) update({ payment: event.data.id });
            }}
          />
        </div>
      )}
      {open && (
        <LedgerDrawer
          paymentId={open}
          onClose={() => update({ payment: null })}
          onChanged={() => loaded.reload()}
        />
      )}
    </>
  );
}
