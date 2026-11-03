import { Fragment } from "react";

export type LinkState = "proven" | "missing";

export interface ChainLink {
  name: string;
  detail: string;
  state: LinkState;
}

const MARK: Record<LinkState, string> = { proven: "M7 12.5l3.2 3.2L17 9", missing: "M8 12h8" };

export function ProofChain({ links, animate = false }: { links: ChainLink[]; animate?: boolean }) {
  return (
    <ol className={`chain${animate ? " chain-animate" : ""}`} aria-label="Proof chain">
      {links.map((link, index) => (
        <Fragment key={link.name}>
          {index > 0 && (
            <li
              className="chain-bar"
              data-state={links[index - 1]?.state === "proven" && link.state === "proven" ? "proven" : "missing"}
              aria-hidden="true"
            />
          )}
          <li className="chain-link" data-state={link.state}>
            <span className="chain-seal">
              <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
                <path d={MARK[link.state]} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <span className="chain-name">{link.name}</span>
            <span className="chain-detail">{link.detail}</span>
            <span className="visually-hidden">{link.state === "proven" ? "on file" : "missing"}</span>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}
