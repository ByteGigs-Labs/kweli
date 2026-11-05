import { Authenticated, Refine } from "@refinedev/core";
import routerProvider, { CatchAllNavigate, NavigateToResource } from "@refinedev/react-router";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router";
import { Shell } from "./layout/Shell";
import { LoginPage } from "./pages/Login";
import { authProvider } from "./providers/authProvider";
import { dataProvider } from "./providers/dataProvider";

const OverviewPage = lazy(() =>
  import("./pages/Overview").then((m) => ({ default: m.OverviewPage })),
);
const LedgerPage = lazy(() => import("./pages/Ledger").then((m) => ({ default: m.LedgerPage })));
const AgreementsPage = lazy(() =>
  import("./pages/agreements/List").then((m) => ({ default: m.AgreementsPage })),
);
const NewAgreementPage = lazy(() =>
  import("./pages/agreements/New").then((m) => ({ default: m.NewAgreementPage })),
);
const AgreementDetailPage = lazy(() =>
  import("./pages/agreements/Detail").then((m) => ({ default: m.AgreementDetailPage })),
);
const InvoicesPage = lazy(() => import("./pages/Invoices").then((m) => ({ default: m.InvoicesPage })));
const AssistantPage = lazy(() =>
  import("./pages/Assistant").then((m) => ({ default: m.AssistantPage })),
);
const PacksPage = lazy(() => import("./pages/packs/List").then((m) => ({ default: m.PacksPage })));
const PackDetailPage = lazy(() =>
  import("./pages/packs/Detail").then((m) => ({ default: m.PackDetailPage })),
);
const PortalPage = lazy(() => import("./pages/Portal").then((m) => ({ default: m.PortalPage })));

export default function App() {
  return (
    <BrowserRouter>
      <Refine
        dataProvider={dataProvider}
        authProvider={authProvider}
        routerProvider={routerProvider}
        resources={[
          { name: "overview", list: "/overview", meta: { label: "Overview" } },
          { name: "ledger", list: "/ledger", meta: { label: "Proof ledger" } },
          { name: "agreements", list: "/agreements", show: "/agreements/:id", create: "/agreements/new" },
          { name: "invoices", list: "/invoices" },
          { name: "assistant", list: "/assistant" },
          { name: "packs", list: "/packs", show: "/packs/:id" },
        ]}
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
            <Route index element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<OverviewPage />} />
            <Route path="/ledger" element={<LedgerPage />} />
            <Route path="/agreements" element={<AgreementsPage />} />
            <Route path="/agreements/new" element={<NewAgreementPage />} />
            <Route path="/agreements/:id" element={<AgreementDetailPage />} />
            <Route path="/invoices" element={<InvoicesPage />} />
            <Route path="/assistant" element={<AssistantPage />} />
            <Route path="/packs" element={<PacksPage />} />
            <Route path="/packs/:id" element={<PackDetailPage />} />
          </Route>
          <Route
            element={
              <Authenticated key="guest" fallback={<Outlet />} loading={<Outlet />}>
                <NavigateToResource resource="overview" />
              </Authenticated>
            }
          >
            <Route path="/login" element={<LoginPage />} />
          </Route>
          <Route
            path="/p/:token"
            element={
              <Suspense fallback={null}>
                <PortalPage />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Refine>
    </BrowserRouter>
  );
}
