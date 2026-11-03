import axios from "axios";

// Same-origin in every environment: Vite proxies /v1 in development and Render rewrites
// /v1 to the API in production, so the session cookie stays first-party.
export const http = axios.create({ withCredentials: true, timeout: 20000 });

const AUTH_PATH = "/v1/auth/";

http.interceptors.response.use(undefined, (failure) => {
  const url: string = failure?.config?.url ?? "";
  const onLogin = window.location.pathname === "/login";
  if (failure?.response?.status === 401 && !url.startsWith(AUTH_PATH) && !onLogin) {
    window.location.assign("/login");
  }
  return Promise.reject(failure);
});

export const statusOf = (failure: unknown) =>
  (failure as { response?: { status?: number } })?.response?.status;
