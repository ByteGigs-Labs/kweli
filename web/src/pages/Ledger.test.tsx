import { render, screen } from "@testing-library/react";
import { LedgerPage } from "./Ledger";

test("an empty ledger tells the freelancer what will appear", async () => {
  render(<LedgerPage />);
  expect(screen.getByRole("heading", { name: "Proof ledger" })).toBeInTheDocument();
  expect(await screen.findByText("No payments yet")).toBeInTheDocument();
});

test("rows show amount and per-rule proof status", async () => {
  render(
    <LedgerPage
      rows={[
        {
          id: "p1",
          received_at: "2026-11-04T10:00:00Z",
          client: "Acme Ltd",
          amount_minor: 80000,
          currency: "USD",
          rules: { P1: "pass", P3: "warn" },
          status: "warn",
        },
      ]}
    />,
  );
  expect(await screen.findByText("Acme Ltd")).toBeInTheDocument();
  expect(screen.getByText("Needs attention")).toBeInTheDocument();
  expect(screen.getAllByText("On file")).toHaveLength(1);
});
