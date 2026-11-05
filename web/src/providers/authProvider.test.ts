import { http } from "../lib/http";
import { authProvider } from "./authProvider";

const failWith = (status: number) =>
  vi.spyOn(http, "post").mockRejectedValueOnce({ response: { status } });

afterEach(() => vi.restoreAllMocks());

test("successful login goes to the ledger", async () => {
  vi.spyOn(http, "post").mockResolvedValueOnce({ data: {} });
  expect(await authProvider.login({ email: "a@b.c", password: "x" })).toEqual({
    success: true,
    redirectTo: "/overview",
  });
});

test.each([
  [401, "That email and password don't match."],
  [429, "Too many attempts. Wait 15 minutes, then try again."],
  [503, "Kweli can't be reached right now. Check your connection and try again."],
])("HTTP %i explains what to do", async (status, message) => {
  failWith(status);
  const result = await authProvider.login({ email: "a@b.c", password: "x" });
  expect(result.success).toBe(false);
  expect(result.error?.message).toBe(message);
});

test("check reports unauthenticated sessions", async () => {
  vi.spyOn(http, "get").mockRejectedValueOnce({ response: { status: 401 } });
  expect(await authProvider.check()).toEqual({ authenticated: false, redirectTo: "/login" });
});

test("401 from any call logs out", async () => {
  expect(await authProvider.onError({ response: { status: 401 } })).toEqual({
    logout: true,
    redirectTo: "/login",
  });
});
