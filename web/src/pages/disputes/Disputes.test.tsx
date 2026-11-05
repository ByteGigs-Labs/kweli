import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "../../lib/api";
import type { Dispute } from "../../types";
import { DisputeDetailPage } from "./Detail";
import { DisputesPage } from "./List";
import { dueText } from "./shared";

const DISPUTE: Dispute = {
  id: "d1",
  paypal_dispute_id: "PP-D-27803",
  reason: "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
  reason_label: "Work not received",
  status: "WAITING_FOR_SELLER_RESPONSE",
  amount_minor: 80000,
  currency: "USD",
  client: "Acme Ltd",
  payment_id: "p1",
  agreement_id: "a1",
  evidence_due_at: "2026-11-14T10:00:00Z",
  outcome: null,
  submitted_at: null,
  source: "webhook",
  created_at: "2026-11-05T10:00:00Z",
  stage: "INQUIRY",
  allowed: ["provide_evidence"],
  buyer_messages: [{ posted_by: "BUYER", time: "", content: "<b>I never got the files</b>" }],
  response: null,
  response_source: null,
  rejected: [],
  evidence: [
    {
      key: "work",
      label: "Delivered work",
      why: "Shows the work was delivered, and when.",
      evidence_type: "PROOF_FOR_SOFTWARE_OR_SERVICE_DELIVERED",
      status: "ready",
      detail: "On file: logo-final.pdf.",
      fix: null,
      notes: [],
      files: [{ name: "Delivered logo-final.pdf", source: "vault" }],
    },
    {
      key: "agreement",
      label: "Accepted agreement",
      why: "Shows the client agreed the scope and the fee before paying.",
      evidence_type: "COPY_OF_CONTRACT",
      status: "ready",
      detail: "Acme Ltd accepted 'Logo design' on 07 Oct 2026.",
      fix: null,
      notes: [],
      files: [{ name: "Agreement Logo design.pdf", source: "agreement" }],
    },
  ],
  strength: "strong",
  submission: null,
  approval_expires_at: null,
  sandbox_tools: true,
  approval_token: null,
};

const PREPARED: Dispute = {
  ...DISPUTE,
  response: "I delivered the work this payment was for.",
  response_source: "standard",
  approval_token: "token-123",
};

const at = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/disputes" element={<DisputesPage />} />
        <Route path="/disputes/:id" element={<DisputeDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("due dates count the days left", () => {
  expect(dueText("2026-11-14T10:00:00Z", new Date("2026-11-05T10:00:00Z"))).toBe("Respond by 14 Nov (9 days left)");
  expect(dueText("2026-11-01T10:00:00Z", new Date("2026-11-05T10:00:00Z"))).toBe("Response was due 1 Nov");
});

test("the list shows each dispute in plain words", async () => {
  vi.spyOn(api, "listDisputes").mockResolvedValue([DISPUTE]);
  at("/disputes");
  expect(await screen.findByText(/Acme Ltd/)).toBeInTheDocument();
  expect(screen.getByText(/Work not received · Waiting for your response/)).toBeInTheDocument();
});

test("the client's words are shown as text, with the evidence Kweli has", async () => {
  vi.spyOn(api, "getDispute").mockResolvedValue(DISPUTE);
  at("/disputes/d1");
  expect(await screen.findByText("<b>I never got the files</b>")).toBeInTheDocument();
  expect(screen.getByText("Strong case")).toBeInTheDocument();
  expect(screen.getByText(/Attaches: Delivered logo-final.pdf/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Sandbox tools" })).toBeInTheDocument();
});

test("nothing is sent until the freelancer confirms, then the approval token is used", async () => {
  vi.spyOn(api, "getDispute").mockResolvedValue(DISPUTE);
  vi.spyOn(api, "prepareDispute").mockResolvedValue(PREPARED);
  const submit = vi.spyOn(api, "submitDispute").mockResolvedValue({
    ...PREPARED,
    approval_token: null,
    submitted_at: "2026-11-05T11:00:00Z",
    submission: {
      at: "2026-11-05T11:00:00Z",
      generic_types: false,
      files: [{ evidence: "work", name: "Delivered logo-final.pdf", sha256: "a".repeat(64), bytes: 9 }],
    },
  });
  at("/disputes/d1");
  await userEvent.click(await screen.findByRole("button", { name: "Prepare the response" }));
  expect(await screen.findByText("I delivered the work this payment was for.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Approve and send" }));
  expect(submit).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Yes, send it to PayPal" }));
  expect(submit).toHaveBeenCalledWith("d1", "token-123");
  const respond = screen.getByRole("region", { name: "Respond" });
  expect(await within(respond).findByText("Sent to PayPal")).toBeInTheDocument();
});

test("after a reload, approving asks the server for a fresh token first", async () => {
  vi.spyOn(api, "getDispute").mockResolvedValue({ ...PREPARED, approval_token: null });
  const approve = vi.spyOn(api, "approveDispute").mockResolvedValue({ ...PREPARED, approval_token: "fresh" });
  const submit = vi.spyOn(api, "submitDispute").mockResolvedValue(PREPARED);
  at("/disputes/d1");
  await userEvent.click(await screen.findByRole("button", { name: "Approve and send" }));
  await userEvent.click(screen.getByRole("button", { name: "Yes, send it to PayPal" }));
  expect(approve).toHaveBeenCalledWith("d1");
  expect(submit).toHaveBeenCalledWith("d1", "fresh");
});

test("an edit that names an unknown amount is shown and not saved", async () => {
  vi.spyOn(api, "getDispute").mockResolvedValue(PREPARED);
  vi.spyOn(api, "editDisputeResponse").mockRejectedValue({
    response: { data: { error: { problems: [{ code: "unknown_amount", message: "USD 50.00 doesn't match.", excerpt: "" }] } } },
  });
  at("/disputes/d1");
  await userEvent.click(await screen.findByRole("button", { name: "Edit" }));
  await userEvent.type(screen.getByLabelText("Response text"), " Refund USD 50.00.");
  await userEvent.click(screen.getByRole("button", { name: "Check and save" }));
  expect(await screen.findByText("USD 50.00 doesn't match.")).toBeInTheDocument();
});
