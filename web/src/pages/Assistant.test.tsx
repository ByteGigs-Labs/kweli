import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as api from "../lib/api";
import type { AgentAction, AgentReply } from "../types";
import { AssistantPage } from "./Assistant";

const ACTION: AgentAction = {
  id: "act1",
  kind: "create_invoice",
  title: "Create and send a PayPal invoice for Acme Ltd",
  details: [
    { label: "To", value: "jordan@acmeltd.com" },
    { label: "Amount", value: "USD 800.00" },
    { label: "Due", value: "11 Nov 2026" },
  ],
  status: "proposed",
  expires_at: "2026-11-04T12:15:00Z",
  token: "single-use-token",
  result: null,
};

const REPLY: AgentReply = {
  reply: "I've prepared the invoice for you to approve.",
  steps: [
    { tool: "find_agreements", label: "Looked up agreements", ok: true },
    { tool: "propose_invoice", label: "Prepared an invoice for your approval", ok: true },
  ],
  actions: [ACTION],
};

afterEach(() => vi.restoreAllMocks());

test("a suggestion asks the assistant and shows what it checked", async () => {
  const ask = vi.spyOn(api, "askAgent").mockResolvedValueOnce({ ...REPLY, actions: [] });
  render(<AssistantPage />);
  await userEvent.click(screen.getByRole("button", { name: "What needs fixing in my ledger?" }));
  expect(ask).toHaveBeenCalledWith([{ role: "user", content: "What needs fixing in my ledger?" }]);
  const steps = await screen.findByRole("list", { name: "What the assistant checked" });
  expect(within(steps).getByText("Looked up agreements")).toBeInTheDocument();
});

test("approving uses the single-use token and shows the result", async () => {
  vi.spyOn(api, "askAgent").mockResolvedValueOnce(REPLY);
  const approve = vi.spyOn(api, "approveAction").mockResolvedValueOnce({
    ...ACTION,
    status: "executed",
    token: null,
    result: { message: "Invoice 0042 sent to jordan@acmeltd.com.", link: "https://pay.test/1" },
  });
  render(<AssistantPage />);
  await userEvent.type(screen.getByLabelText("Ask the assistant"), "Invoice Acme for the logo{enter}");
  const card = await screen.findByRole("region", { name: /Approval: Create and send/ });
  expect(within(card).getByText("jordan@acmeltd.com")).toBeInTheDocument();
  expect(within(card).getByText("USD 800.00")).toBeInTheDocument();
  expect(within(card).getByText(/Nothing happens until you approve/)).toBeInTheDocument();
  await userEvent.click(within(card).getByRole("button", { name: "Approve" }));
  expect(approve).toHaveBeenCalledWith("act1", "single-use-token");
  expect(await within(card).findByRole("status")).toHaveTextContent("Invoice 0042 sent");
  expect(within(card).queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
});

test("declining closes the card", async () => {
  vi.spyOn(api, "askAgent").mockResolvedValueOnce(REPLY);
  vi.spyOn(api, "rejectAction").mockResolvedValueOnce({
    ...ACTION,
    status: "rejected",
    token: null,
    result: { message: "You declined this." },
  });
  render(<AssistantPage />);
  await userEvent.type(screen.getByLabelText("Ask the assistant"), "Invoice Acme{enter}");
  const card = await screen.findByRole("region", { name: /Approval/ });
  await userEvent.click(within(card).getByRole("button", { name: "Decline" }));
  expect(await within(card).findByText("Declined")).toBeInTheDocument();
});

test("when the assistant isn't available the question is kept", async () => {
  vi.spyOn(api, "askAgent").mockRejectedValueOnce({
    response: { status: 503, data: { error: { message: "The assistant isn't set up here yet." } } },
  });
  render(<AssistantPage />);
  await userEvent.type(screen.getByLabelText("Ask the assistant"), "Hello there{enter}");
  expect(await screen.findByRole("alert")).toHaveTextContent("isn't set up here yet");
  expect(screen.getByLabelText("Ask the assistant")).toHaveValue("Hello there");
});
