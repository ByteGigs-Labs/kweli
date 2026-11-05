import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "../../lib/api";
import type { Pack } from "../../types";
import { PackDetailPage } from "./Detail";
import { monthsBack, PacksPage } from "./List";

const PACK: Pack = {
  id: "k1",
  period_start: "2026-08-06",
  period_end: "2026-11-05",
  letter_source: "standard",
  payments: 11,
  statuses: { pass: 5, warn: 3, fail: 2, pending: 1 },
  totals: [{ currency: "USD", amount_minor: 835000 }],
  created_at: "2026-11-05T09:00:00Z",
  updated_at: null,
  pdf_document_id: "doc-pdf",
  zip_document_id: "doc-zip",
  letter:
    "To PayPal's account review team,\n\nI received 11 payments totalling USD 8,350.00 [T1].\n\nKind regards,\nAmina",
  summary: {
    payments: 11,
    clients: 5,
    documents: 29,
    attached: 29,
    left_out: [],
    ai_rejected: [{ code: "unknown_ref", message: "[D40] isn't in this pack.", excerpt: "[D40]" }],
    letter_attempts: 2,
    pdf_sha256: "a".repeat(64),
    zip_sha256: "b".repeat(64),
    audit_head: `sha256:${"c".repeat(64)}`,
  },
};

const at = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/packs" element={<PacksPage />} />
        <Route path="/packs/:id" element={<PackDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("presets cover whole months ending today", () => {
  expect(monthsBack(3, new Date(2026, 10, 5))).toEqual({ start: "2026-08-06", end: "2026-11-05" });
});

test("building a pack sends the chosen period and opens it", async () => {
  vi.spyOn(api, "listPacks").mockResolvedValue([]);
  const create = vi.spyOn(api, "createPack").mockResolvedValue(PACK);
  vi.spyOn(api, "getPack").mockResolvedValue(PACK);
  at("/packs");
  expect(await screen.findByText("No packs yet.")).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Last 3 months"));
  await userEvent.click(screen.getByRole("button", { name: "Build the pack" }));
  const [start, end] = create.mock.calls[0] ?? ["", ""];
  expect(start < end).toBe(true);
  expect(await screen.findByRole("heading", { name: /Pack for/ })).toBeInTheDocument();
});

test("the pack shows its letter with citations and says why the AI draft was not used", async () => {
  vi.spyOn(api, "getPack").mockResolvedValue(PACK);
  at("/packs/k1");
  expect(await screen.findByText("[T1]")).toHaveClass("cite");
  expect(screen.getByText("Kweli standard letter")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Why Kweli didn't use the AI's draft"));
  expect(screen.getByText("[D40] isn't in this pack.")).toBeInTheDocument();
  const downloads = screen.getByRole("region", { name: "Downloads" });
  expect(within(downloads).getByText(/2 missing proof/)).toBeInTheDocument();
});

test("an edit that fails the checks is shown and not saved", async () => {
  vi.spyOn(api, "getPack").mockResolvedValue(PACK);
  vi.spyOn(api, "editPackLetter").mockRejectedValue({
    response: {
      data: {
        error: {
          message: "rejected",
          problems: [{ code: "wrong_amount", message: "[P1] was USD 800.00, not USD 900.00.", excerpt: "" }],
        },
      },
    },
  });
  at("/packs/k1");
  await userEvent.click(await screen.findByRole("button", { name: "Edit the letter" }));
  await userEvent.type(screen.getByLabelText("Letter text"), " Extra.");
  await userEvent.click(screen.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByText("[P1] was USD 800.00, not USD 900.00.")).toBeInTheDocument();
  expect(screen.getByLabelText("Letter text")).toBeInTheDocument();
});

test("a passing edit replaces the letter", async () => {
  vi.spyOn(api, "getPack").mockResolvedValue(PACK);
  vi.spyOn(api, "editPackLetter").mockResolvedValue({ ...PACK, letter_source: "edited", letter: PACK.letter + " Thanks." });
  at("/packs/k1");
  await userEvent.click(await screen.findByRole("button", { name: "Edit the letter" }));
  await userEvent.click(screen.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByText("Edited by you, checked")).toBeInTheDocument();
  expect(screen.queryByLabelText("Letter text")).not.toBeInTheDocument();
});
