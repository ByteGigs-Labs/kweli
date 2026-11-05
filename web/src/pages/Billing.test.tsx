import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import * as api from "../lib/api";
import type { Billing } from "../types";
import { BillingPage } from "./Billing";

const refetch = vi.fn();
vi.mock("@refinedev/core", () => ({ useGetIdentity: () => ({ refetch }) }));

const FREE: Billing = {
  plan: "free",
  enabled: true,
  price: "9.00",
  currency: "USD",
  features: ["Compliance Packs", "Dispute defender", "Unlimited clients"],
  free_client_limit: 3,
  subscription_status: null,
  next_billing_at: null,
};

const at = (url = "/billing") =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <BillingPage />
    </MemoryRouter>,
  );

const assign = vi.fn();

beforeEach(() => {
  Object.defineProperty(window, "location", { value: { ...window.location, assign }, writable: true });
});

afterEach(() => {
  vi.restoreAllMocks();
  assign.mockReset();
  refetch.mockReset();
});

test("a free user can upgrade on PayPal's own page", async () => {
  vi.spyOn(api, "getBilling").mockResolvedValue(FREE);
  vi.spyOn(api, "startCheckout").mockResolvedValue({
    approve_url: "https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-1",
  });
  at();
  expect(await screen.findByText("USD 9.00")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Upgrade with PayPal" }));
  expect(assign).toHaveBeenCalledWith("https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-1");
});

test("a checkout link that isn't PayPal's is never followed", async () => {
  vi.spyOn(api, "getBilling").mockResolvedValue(FREE);
  vi.spyOn(api, "startCheckout").mockResolvedValue({ approve_url: "https://paypal.com.evil.test/x" });
  at();
  await userEvent.click(await screen.findByRole("button", { name: "Upgrade with PayPal" }));
  expect(assign).not.toHaveBeenCalled();
  expect(await screen.findByRole("alert")).toHaveTextContent("PayPal checkout couldn't start");
});

test("coming back from PayPal confirms the subscription with the server", async () => {
  vi.spyOn(api, "getBilling").mockResolvedValue(FREE);
  const confirm = vi
    .spyOn(api, "confirmBilling")
    .mockResolvedValue({ ...FREE, plan: "pro", subscription_status: "ACTIVE" });
  at("/billing?paypal=approved&subscription_id=I-SUB1&ba_token=BA-1");
  expect(await screen.findByText("Welcome to Kweli Pro.")).toBeInTheDocument();
  expect(confirm).toHaveBeenCalledTimes(1);
  expect(confirm).toHaveBeenCalledWith("I-SUB1");
  expect(refetch).toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Cancel subscription" })).toBeInTheDocument();
});

test("leaving PayPal early says nothing was charged", async () => {
  vi.spyOn(api, "getBilling").mockResolvedValue(FREE);
  at("/billing?paypal=cancelled");
  expect(await screen.findByText(/Nothing was charged/)).toBeInTheDocument();
});
