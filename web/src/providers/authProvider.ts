import type { AuthProvider } from "@refinedev/core";
import { http, statusOf } from "../lib/http";
import type { Identity } from "../types";

export const authProvider: AuthProvider = {
  login: async ({ email, password }) => {
    try {
      await http.post("/v1/auth/login", { email, password });
      return { success: true, redirectTo: "/ledger" };
    } catch (failure) {
      const status = statusOf(failure);
      return {
        success: false,
        error: {
          name: "Sign in failed",
          message:
            status === 429
              ? "Too many attempts. Wait 15 minutes, then try again."
              : status === 401
                ? "That email and password don't match."
                : "Kweli can't be reached right now. Check your connection and try again.",
        },
      };
    }
  },

  logout: async () => {
    await http.post("/v1/auth/logout").catch(() => undefined);
    return { success: true, redirectTo: "/login" };
  },

  check: async () => {
    try {
      await http.get("/v1/auth/me");
      return { authenticated: true };
    } catch {
      return { authenticated: false, redirectTo: "/login" };
    }
  },

  getIdentity: async () => {
    try {
      return (await http.get<Identity>("/v1/auth/me")).data;
    } catch {
      return null;
    }
  },

  onError: async (error) => {
    if (statusOf(error) === 401) {
      return { logout: true, redirectTo: "/login" };
    }
    return { error };
  },
};
