import { Authenticated, Refine } from "@refinedev/core";
import routerProvider, { CatchAllNavigate, NavigateToResource } from "@refinedev/react-router";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router";
import { Shell } from "./layout/Shell";
import { LoginPage } from "./pages/Login";
import { authProvider } from "./providers/authProvider";
import { dataProvider } from "./providers/dataProvider";

const LedgerPage = lazy(() => import("./pages/Ledger").then((m) => ({ default: m.LedgerPage })));

export default function App() {
  return (
    <BrowserRouter>
      <Refine
        dataProvider={dataProvider}
        authProvider={authProvider}
        routerProvider={routerProvider}
        resources={[{ name: "ledger", list: "/ledger", meta: { label: "Proof ledger" } }]}
        options={{ syncWithLocation: false, disableTelemetry: true }}
      >
        <Routes>
          <Route
            element={
              <Authenticated key="app" fallback={<CatchAllNavigate to="/login" />}>
                <Suspense fallback={null}>
                  <Shell />
                </Suspense>
              </Authenticated>
            }
          >
            <Route index element={<Navigate to="/ledger" replace />} />
            <Route path="/ledger" element={<LedgerPage />} />
          </Route>
          <Route
            element={
              <Authenticated key="guest" fallback={<Outlet />} loading={<Outlet />}>
                <NavigateToResource resource="ledger" />
              </Authenticated>
            }
          >
            <Route path="/login" element={<LoginPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Refine>
    </BrowserRouter>
  );
}
