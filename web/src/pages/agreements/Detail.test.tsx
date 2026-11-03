import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "../../lib/api";
import type { Agreement, Invoice } from "../../types";
import { AgreementDetailPage } from "./Detail";

const AGREEMENT: Agreement = {
  id: "a1",
  client: { id: "c1", name: "Acme Ltd", email: "jordan@acmeltd.com", country: "US", created_at: "" },
  title: "Logo design",
  scope: "A logo",
  deliverables: ["3 concepts"],
  amount: "800.00",
  amount_minor: 80000,
  currency: "USD",
  due_date: "2026-11-20",
  status: "accepted",
  sent_at: "2026-11-03T10:00:00Z",
  accepted_at: "2026-11-03T12:00:00Z",
  created_at: "2026-11-03T09:00:00Z",
  invoice_id: null,
  terms: ["Amina Wanjiru will deliver the work below for Acme Ltd."],
};

const INVOICE: Invoice = {
  id: "i1",
  agreement_id: "a1",
  client_id: "c1",
  paypal_invoice_id: "INV2-1",
  number: "0042",
  description: "Logo design",
  amount_minor: 80000,
  currency: "USD",
  due_date: "2026-11-20",
  status: "draft",
  payer_view_url: null,
  sent_at: null,
  created_at: "",
};

const renderDetail = () =>
  render(
    <MemoryRouter initialEntries={["/agreements/a1"]}>
      <Routes>
        <Route path="/agreements/:id" element={<AgreementDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("draft first, then an explicit send that names the recipient", async () => {
  vi.spyOn(api, "getAgreement").mockResolvedValue(AGREEMENT);
  vi.spyOn(api, "getInvoice").mockResolvedValue(INVOICE);
  const create = vi.spyOn(api, "createInvoice").mockResolvedValueOnce(INVOICE);
  const send = vi.spyOn(api, "sendInvoice").mockResolvedValueOnce({
    ...INVOICE,
    status: "sent",
    sent_at: "2026-11-04T08:00:00Z",
    payer_view_url: "https://www.sandbox.paypal.com/invoice/p/#INV2-1",
  });
  renderDetail();
  await userEvent.click(await screen.findByRole("button", { name: "Create PayPal draft" }));
  expect(create).toHaveBeenCalledWith("a1", "2026-11-20");
  const sendButton = await screen.findByRole("button", { name: "Send to jordan@acmeltd.com via PayPal" });
  expect(send).not.toHaveBeenCalled();
  vi.spyOn(api, "getInvoice").mockResolvedValue({ ...INVOICE, status: "sent", sent_at: "2026-11-04T08:00:00Z" });
  await userEvent.click(sendButton);
  expect(send).toHaveBeenCalledWith("i1");
  expect(await screen.findByRole("heading", { name: "Invoice sent" })).toBeInTheDocument();
});

test("before acceptance the page offers an acceptance link, not an invoice", async () => {
  vi.spyOn(api, "getAgreement").mockResolvedValue({ ...AGREEMENT, status: "draft", accepted_at: null });
  renderDetail();
  expect(await screen.findByRole("button", { name: "Create acceptance link" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create PayPal draft" })).not.toBeInTheDocument();
  expect(screen.getByText("Not accepted yet")).toBeInTheDocument();
});
