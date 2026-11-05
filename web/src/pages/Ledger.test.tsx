import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import * as api from "../lib/api";
import type { LedgerDetail, LedgerRow } from "../types";
import { LedgerPage } from "./Ledger";

const ROW: LedgerRow = {
  id: "p1",
  received_at: "2026-11-04T10:00:00Z",
  client: "Kilele Tours",
  amount_minor: 60000,
  currency: "USD",
  rules: { P1: "pass", P2: "pass", P3: "warn", P4: "pass", P5: "fail", P6: "pass", P7: "pass" },
  status: "fail",
};

const DETAIL: LedgerDetail = {
  ...ROW,
  payer: "Mwangi Holdings",
  payment_type: "invoice",
  agreement_id: "a1",
  invoice_number: "0008",
  linked_by: "invoice",
  payer_confirmation: null,
  chain: [
    { name: "Agreement", proven: true, detail: "Accepted 27 Oct" },
    { name: "Invoice", proven: true, detail: "No. 0008" },
    { name: "Payment", proven: true, detail: "Paid 4 Nov" },
    { name: "Deliverable", proven: false, detail: "Not uploaded" },
  ],
  flags: [
    { rule: "P3", status: "warn", explanation: "Paid by Mwangi Holdings, not Kilele Tours.",
      fix: "Ask Kilele Tours to confirm in writing that this payment is theirs, and upload it." },
    { rule: "P5", status: "fail", explanation: "No delivered work is attached.",
      fix: "Upload the final file, or a document linking to it." },
  ],
};

const OTHER: LedgerRow = {
  ...ROW,
  id: "p2",
  client: "Acme Ltd",
  amount_minor: 80000,
  rules: Object.fromEntries(Object.keys(ROW.rules).map((rule) => [rule, "pass"])),
  status: "pass",
};

const renderLedger = (url = "/ledger") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <LedgerPage />
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("an empty ledger tells the freelancer what will appear", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValueOnce([]);
  renderLedger();
  expect(screen.getByRole("heading", { name: "Proof ledger" })).toBeInTheDocument();
  expect(await screen.findByText("No payments yet")).toBeInTheDocument();
});

test("rows show amount, per-rule badges and a summary", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValueOnce([ROW]);
  renderLedger();
  expect(await screen.findByText("Kilele Tours")).toBeInTheDocument();
  expect(screen.getByText(/USD\s600\.00/)).toBeInTheDocument();
  const summary = screen.getByRole("list", { name: "Summary" });
  expect(within(summary).getByText("missing proof")).toBeInTheDocument();
});

test("selecting a payment explains each check and offers the fix", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValue([ROW]);
  vi.spyOn(api, "getLedgerEntry").mockResolvedValue(DETAIL);
  renderLedger();
  await userEvent.click(await screen.findByText("Kilele Tours"));
  const drawer = await screen.findByRole("dialog");
  expect(await within(drawer).findByText("Paid by Mwangi Holdings, not Kilele Tours.")).toBeInTheDocument();
  expect(within(drawer).getByText(/confirm in writing/)).toBeInTheDocument();
  expect(within(drawer).getByRole("button", { name: "Upload delivered work" })).toBeInTheDocument();
  expect(within(drawer).getByRole("button", { name: "Upload the client's confirmation" })).toBeInTheDocument();
  expect(within(drawer).queryByText("Link to an agreement")).not.toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("the summary chips filter the grid and can be cleared", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValue([ROW, OTHER]);
  renderLedger();
  expect(await screen.findByText("Acme Ltd")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /missing proof/ }));
  expect(screen.getByRole("button", { name: /missing proof/ })).toHaveAttribute("aria-pressed", "true");
  await waitFor(() => expect(screen.queryByText("Acme Ltd")).not.toBeInTheDocument());
  expect(screen.getByText("Kilele Tours")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  expect(await screen.findByText("Acme Ltd")).toBeInTheDocument();
});

test("a client link from the overview filters to that client", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValue([ROW, OTHER]);
  renderLedger("/ledger?client=Acme%20Ltd");
  expect(await screen.findByText("Acme Ltd")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("Kilele Tours")).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: /Client: Acme Ltd/ }));
  expect(await screen.findByText("Kilele Tours")).toBeInTheDocument();
});

test("a payment link opens its drawer, and an unlinked payment can be linked", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValue([ROW]);
  vi.spyOn(api, "getLedgerEntry").mockResolvedValue({
    ...DETAIL,
    agreement_id: null,
    invoice_number: null,
    linked_by: null,
    flags: [],
  });
  vi.spyOn(api, "listAgreements").mockResolvedValue([
    {
      id: "a9",
      client: { id: "c1", name: "D. Otieno", email: "d@mail.com", country: null, created_at: "" },
      title: "Event poster",
      scope: "",
      deliverables: [],
      amount: "150.00",
      amount_minor: 15000,
      currency: "USD",
      due_date: null,
      status: "sent",
      sent_at: null,
      accepted_at: null,
      created_at: "",
      invoice_id: null,
    },
  ]);
  const link = vi.spyOn(api, "linkPaymentAgreement").mockResolvedValue(DETAIL);
  renderLedger("/ledger?payment=p1");
  const drawer = await screen.findByRole("dialog");
  const select = await within(drawer).findByRole("combobox", { name: "Agreement" });
  await userEvent.selectOptions(select, "a9");
  await userEvent.click(within(drawer).getByRole("button", { name: "Link" }));
  expect(link).toHaveBeenCalledWith("p1", "a9");
});

test("the by-client view summarises readiness and drills into a client", async () => {
  vi.spyOn(api, "listLedger").mockResolvedValue([ROW, OTHER]);
  vi.spyOn(api, "getReadiness").mockResolvedValue({
    score: 80,
    band: "nearly",
    thresholds: { ready: 90, nearly: 70 },
    payments: 2,
    statuses: { pass: 1, warn: 0, fail: 1, pending: 0 },
    checks: { pass: 10, warn: 1, fail: 1, pending: 0 },
    large_payments: 0,
    fix_total: 1,
    fix_next: [],
    clients: [
      {
        client: "Kilele Tours",
        payments: 1,
        totals: [{ currency: "USD", amount_minor: 60000 }],
        statuses: { pass: 0, warn: 0, fail: 1, pending: 0 },
        score: 75,
      },
    ],
  });
  renderLedger("/ledger?view=clients");
  expect(await screen.findByRole("img", { name: "Readiness 75 out of 100" })).toBeInTheDocument();
  await userEvent.click(screen.getByText("Kilele Tours"));
  expect(await screen.findByRole("button", { name: /Client: Kilele Tours/ })).toBeInTheDocument();
});
