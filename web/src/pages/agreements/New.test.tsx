import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "../../lib/api";
import { NewAgreementPage } from "./New";

const THREAD = "Jordan (jordan@acmeltd.com): logo for $800 by 20 Nov. Amina: deal.";

function renderPage() {
  render(
    <MemoryRouter initialEntries={["/agreements/new"]}>
      <Routes>
        <Route path="/agreements/new" element={<NewAgreementPage />} />
        <Route path="/agreements/:id" element={<p>Saved page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.restoreAllMocks());

test("fills the form from the conversation and flags what's missing", async () => {
  vi.spyOn(api, "readThread").mockResolvedValueOnce({
    client_name: null,
    client_email: "jordan@acmeltd.com",
    title: "Logo design",
    scope: null,
    deliverables: ["Logo files"],
    amount: "800",
    currency: "USD",
    due_date: null,
    missing: ["client_name", "due_date"],
    notes: ["The email the AI suggested isn't in the thread, so it was left out."],
  });
  renderPage();
  await userEvent.type(screen.getByLabelText("Conversation with the client"), THREAD);
  await userEvent.click(screen.getByRole("button", { name: "Fill in from conversation" }));
  expect(await screen.findByLabelText("Client's PayPal email")).toHaveValue("jordan@acmeltd.com");
  expect(screen.getByLabelText("Fee")).toHaveValue("800");
  expect(screen.getAllByText("Not in the thread. Add it.")).toHaveLength(2);
  expect(screen.getByText(/isn't in the thread, so it was left out/)).toBeInTheDocument();
});

test("without AI the freelancer can still fill it in by hand and save", async () => {
  vi.spyOn(api, "readThread").mockRejectedValueOnce({
    response: { status: 503, data: { error: { message: "Fill in the agreement by hand." } } },
  });
  const create = vi.spyOn(api, "createAgreement").mockResolvedValueOnce({ id: "a1" } as never);
  renderPage();
  await userEvent.type(screen.getByLabelText("Conversation with the client"), THREAD);
  await userEvent.click(screen.getByRole("button", { name: "Fill in from conversation" }));
  expect(await screen.findByText("Fill in the agreement by hand.")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Client name"), "Acme Ltd");
  await userEvent.type(screen.getByLabelText("Client's PayPal email"), "jordan@acmeltd.com");
  await userEvent.type(screen.getByLabelText("Work"), "Logo design");
  await userEvent.type(screen.getByLabelText("Deliverables, one per line"), "Logo{enter}Brand sheet");
  await userEvent.type(screen.getByLabelText("Fee"), "800");
  await userEvent.click(screen.getByRole("button", { name: "Save agreement" }));
  expect(await screen.findByText("Saved page")).toBeInTheDocument();
  expect(create).toHaveBeenCalledWith(
    expect.objectContaining({
      client: { name: "Acme Ltd", email: "jordan@acmeltd.com" },
      deliverables: ["Logo", "Brand sheet"],
      amount: "800",
      scope: "Logo design",
      due_date: null,
    }),
  );
});
