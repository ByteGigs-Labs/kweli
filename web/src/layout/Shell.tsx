import { useGetIdentity, useLogout } from "@refinedev/core";
import { NavLink, Outlet } from "react-router";
import { Wordmark } from "../components/Wordmark";
import type { Identity } from "../types";
import "../styles/shell.css";

const NAV: { to: string; label: string; ready: boolean }[] = [
  { to: "/ledger", label: "Proof ledger", ready: true },
  { to: "/agreements", label: "Agreements", ready: true },
  { to: "/invoices", label: "Invoices", ready: true },
  { to: "/disputes", label: "Disputes", ready: false },
  { to: "/packs", label: "Compliance packs", ready: false },
];

export function Shell() {
  const { data: identity } = useGetIdentity<Identity>();
  const { mutate: logout } = useLogout();

  return (
    <div className="shell">
      <aside className="rail">
        <Wordmark />
        <nav aria-label="Main">
          <ul>
            {NAV.map((item) => (
              <li key={item.to}>
                {item.ready ? (
                  <NavLink to={item.to}>{item.label}</NavLink>
                ) : (
                  <a aria-disabled="true">
                    {item.label}
                    <span className="rail-soon">Soon</span>
                  </a>
                )}
              </li>
            ))}
          </ul>
        </nav>
        <div className="rail-user">
          <span>
            <strong>{identity?.name ?? "…"}</strong>
            <br />
            {identity ? (identity.plan === "pro" ? "Kweli Pro" : "Free plan") : ""}
          </span>
          <button type="button" className="button button-quiet" onClick={() => logout()}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
