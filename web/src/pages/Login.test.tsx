import { Refine } from "@refinedev/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AuthProvider } from "@refinedev/core";
import { MemoryRouter } from "react-router";
import { LoginPage } from "./Login";

function renderLogin(login: AuthProvider["login"]) {
  const auth: AuthProvider = {
    login,
    logout: async () => ({ success: true }),
    check: async () => ({ authenticated: false }),
    onError: async () => ({}),
  };
  render(
    <MemoryRouter>
      <Refine authProvider={auth} options={{ disableTelemetry: true }}>
        <LoginPage />
      </Refine>
    </MemoryRouter>,
  );
}

test("shows why sign in failed", async () => {
  renderLogin(async () => ({
    success: false,
    error: { name: "Sign in failed", message: "That email and password don't match." },
  }));
  await userEvent.type(screen.getByLabelText("Email"), "amina@kweli.test");
  await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
});

test("sends the typed credentials", async () => {
  const login = vi.fn(async () => ({ success: true }));
  renderLogin(login);
  await userEvent.type(screen.getByLabelText("Email"), "amina@kweli.test");
  await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(login).toHaveBeenCalledWith({ email: "amina@kweli.test", password: "correct-horse-battery" });
});
