import { render, screen, within } from "@testing-library/react";
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

const renderLedger = () =>
  render(
    <MemoryRouter>
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
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
