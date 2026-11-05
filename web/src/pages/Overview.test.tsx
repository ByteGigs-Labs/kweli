import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import * as api from "../lib/api";
import type { Readiness } from "../types";
import { OverviewPage } from "./Overview";

const READINESS: Readiness = {
  score: 88,
  band: "nearly",
  thresholds: { ready: 90, nearly: 70 },
  payments: 11,
  statuses: { pass: 5, warn: 3, fail: 2, pending: 1 },
  checks: { pass: 56, warn: 3, fail: 6, pending: 1 },
  large_payments: 1,
  fix_total: 2,
  fix_next: [
    {
      payment_id: "p-otieno",
      agreement_id: null,
      client: "D. Otieno",
      amount_minor: 15000,
      currency: "USD",
      received_at: "2026-11-02T08:00:00Z",
      status: "fail",
      points: 8,
      steps: [
        { rule: "P4", status: "fail", problem: "There's no agreement for this work.", fix: "Link this payment to its agreement." },
      ],
    },
    {
      payment_id: "p-kilele",
      agreement_id: "a1",
      client: "Kilele Tours",
      amount_minor: 60000,
      currency: "USD",
      received_at: "2026-10-27T08:00:00Z",
      status: "warn",
      points: 1,
      steps: [
        { rule: "P3", status: "warn", problem: "Paid by Mwangi Holdings, not Kilele Tours.", fix: "Ask Kilele Tours to confirm." },
      ],
    },
  ],
  clients: [],
};

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname + location.search}</p>;
}

const renderOverview = () =>
  render(
    <MemoryRouter initialEntries={["/overview"]}>
      <Routes>
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/ledger" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("shows the score, what it means and the fixes in priority order", async () => {
  vi.spyOn(api, "getReadiness").mockResolvedValue(READINESS);
  renderOverview();
  expect(await screen.findByRole("img", { name: "Readiness 88 out of 100" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Nearly ready" })).toBeInTheDocument();
  expect(screen.getByText(/56 of 65 checks pass across 11 payments/)).toBeInTheDocument();
  expect(screen.getByText(/One payment is much larger than usual/)).toBeInTheDocument();
  const cards = screen.getAllByRole("heading", { level: 3 });
  expect(cards.map((card) => card.textContent?.replace(/\s+/g, " "))).toEqual([
    "D. Otieno · USD 150.00",
    "Kilele Tours · USD 600.00",
  ]);
  expect(screen.getByText("+8 points")).toBeInTheDocument();
});

test("fixing a payment opens it in the ledger", async () => {
  vi.spyOn(api, "getReadiness").mockResolvedValue(READINESS);
  renderOverview();
  const first = (await screen.findByText("D. Otieno · USD 150.00")).closest("li") as HTMLElement;
  await userEvent.click(within(first).getByRole("button", { name: "Fix this payment" }));
  expect(screen.getByTestId("where")).toHaveTextContent("/ledger?payment=p-otieno");
});

test("with nothing to fix it says so", async () => {
  vi.spyOn(api, "getReadiness").mockResolvedValue({
    ...READINESS,
    score: 100,
    band: "ready",
    fix_total: 0,
    fix_next: [],
    large_payments: 0,
    statuses: { pass: 3, warn: 0, fail: 0, pending: 0 },
  });
  renderOverview();
  expect(await screen.findByRole("heading", { name: "Ready for a review" })).toBeInTheDocument();
  expect(screen.getByText("Nothing to fix. Every payment has its proof on file.")).toBeInTheDocument();
});

test("before any payment it points to the first agreement", async () => {
  vi.spyOn(api, "getReadiness").mockResolvedValue({ ...READINESS, score: null, band: "no_payments", payments: 0 });
  renderOverview();
  expect(await screen.findByText("No payments yet")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "agreement" })).toHaveAttribute("href", "/agreements/new");
});
