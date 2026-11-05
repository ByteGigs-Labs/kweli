import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { createPack, errorMessage, listPacks, needsPro } from "../../lib/api";
import { formatMoney } from "../../lib/money";
import { useAsync } from "../../lib/useAsync";
import type { PackSummary } from "../../types";
import "../../styles/packs.css";

const PRESETS = [
  { months: 3, label: "Last 3 months" },
  { months: 6, label: "Last 6 months" },
  { months: 12, label: "Last 12 months" },
];

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

export function monthsBack(months: number, today = new Date()) {
  const start = new Date(today);
  start.setMonth(start.getMonth() - months);
  start.setDate(start.getDate() + 1);
  return { start: iso(start), end: iso(today) };
}

export const longDate = (value: string) =>
  new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

export const SOURCE_LABEL = {
  ai: "Drafted by AI, checked",
  standard: "Kweli standard letter",
  edited: "Edited by you, checked",
} as const;

function PackRow({ pack }: { pack: PackSummary }) {
  return (
    <li className="pack-row">
      <Link to={`/packs/${pack.id}`} className="pack-row-link">
        <strong>
          {longDate(pack.period_start)} – {longDate(pack.period_end)}
        </strong>
        <span>
          {pack.payments} payment{pack.payments === 1 ? "" : "s"} ·{" "}
          {pack.totals.map((total) => formatMoney(total.amount_minor, total.currency)).join(", ")}
        </span>
        <span className="muted">
          {SOURCE_LABEL[pack.letter_source]} · made {longDate(pack.created_at)}
        </span>
      </Link>
    </li>
  );
}

export function PacksPage() {
  const packs = useAsync(listPacks, []);
  const navigate = useNavigate();
  const [preset, setPreset] = useState<number | "custom">(12);
  const [custom, setCustom] = useState(monthsBack(3));
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [upgrade, setUpgrade] = useState(false);

  const period = preset === "custom" ? custom : monthsBack(preset);

  const build = async () => {
    setBusy(true);
    setFailed(null);
    try {
      const pack = await createPack(period.start, period.end);
      navigate(`/packs/${pack.id}`);
    } catch (failure) {
      setUpgrade(needsPro(failure));
      setFailed(errorMessage(failure, "The pack couldn't be built. Try again."));
      setBusy(false);
    }
  };

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Compliance packs</h1>
          <p>
            When PayPal asks what your payments were for, send one pack: a cover letter, every payment
            mapped to its proof, and the documents themselves.
          </p>
        </div>
      </header>

      <section className="pack-builder" aria-labelledby="builder-title">
        <h2 id="builder-title">Build a pack</h2>
        <fieldset className="pack-periods">
          <legend>Payments received in</legend>
          {PRESETS.map((item) => (
            <label key={item.months} className="pack-period">
              <input
                type="radio"
                name="period"
                checked={preset === item.months}
                onChange={() => setPreset(item.months)}
              />
              {item.label}
            </label>
          ))}
          <label className="pack-period">
            <input
              type="radio"
              name="period"
              checked={preset === "custom"}
              onChange={() => setPreset("custom")}
            />
            Choose dates
          </label>
        </fieldset>
        {preset === "custom" && (
          <div className="pack-dates">
            <div className="field">
              <label htmlFor="pack-from">From</label>
              <input
                id="pack-from"
                type="date"
                value={custom.start}
                max={custom.end}
                onChange={(event) => setCustom({ ...custom, start: event.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor="pack-to">To</label>
              <input
                id="pack-to"
                type="date"
                value={custom.end}
                min={custom.start}
                max={iso(new Date())}
                onChange={(event) => setCustom({ ...custom, end: event.target.value })}
              />
            </div>
          </div>
        )}
        <p className="muted">
          {longDate(period.start)} to {longDate(period.end)}. Kweli drafts the letter, then checks every
          citation and amount against your records before anything is saved.
        </p>
        <div>
          <button type="button" className="button" onClick={build} disabled={busy}>
            {busy ? "Building and checking…" : "Build the pack"}
          </button>
        </div>
        {failed && (
          <p className="alert" role="alert">
            {failed} {upgrade && <Link to="/billing">See Kweli Pro</Link>}
          </p>
        )}
      </section>

      <section aria-labelledby="packs-title" className="pack-history">
        <h2 id="packs-title">Your packs</h2>
        {packs.error !== undefined && (
          <p className="alert" role="alert">
            Your packs couldn't load.
          </p>
        )}
        {packs.data && packs.data.length === 0 && <p className="muted">No packs yet.</p>}
        {packs.data && packs.data.length > 0 && (
          <ul className="pack-rows">
            {packs.data.map((pack) => (
              <PackRow key={pack.id} pack={pack} />
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
