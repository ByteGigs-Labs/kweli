import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import * as api from "../lib/api";
import type { PortalAgreement } from "../types";
import { PortalPage } from "./Portal";

const AGREEMENT: PortalAgreement = {
  freelancer: "Amina Wanjiru",
  client: "Acme Ltd",
  title: "Logo design",
  deliverables: ["3 concepts"],
  amount: "800.00",
  currency: "USD",
  due_date: "2026-11-20",
  terms: ["Amina Wanjiru will deliver the work below for Acme Ltd."],
  status: "sent",
  accepted_at: null,
};

const renderPortal = () =>
  render(
    <MemoryRouter initialEntries={["/p/token-123"]}>
      <Routes>
        <Route path="/p/:token" element={<PortalPage />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => vi.restoreAllMocks());

test("the client must confirm before accepting", async () => {
  vi.spyOn(api, "viewPortal").mockResolvedValueOnce(AGREEMENT);
  const accept = vi
    .spyOn(api, "acceptPortal")
    .mockResolvedValueOnce({ ...AGREEMENT, status: "accepted", accepted_at: "2026-11-04T09:00:00Z" });
  renderPortal();
  const button = await screen.findByRole("button", { name: "Accept agreement" });
  expect(button).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(button);
  expect(accept).toHaveBeenCalledWith("token-123");
  expect(await screen.findByRole("status")).toHaveTextContent("You accepted this agreement");
});

test("an expired link explains what to do", async () => {
  vi.spyOn(api, "viewPortal").mockRejectedValueOnce({
    response: { status: 410, data: { error: { message: "This link has expired. Ask the freelancer for a new one." } } },
  });
  renderPortal();
  expect(await screen.findByText(/Ask the freelancer for a new one/)).toBeInTheDocument();
});
