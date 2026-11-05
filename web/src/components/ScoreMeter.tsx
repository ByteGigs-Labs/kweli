import type { ReadinessBand } from "../types";

export const BAND_LABEL: Record<ReadinessBand, string> = {
  ready: "Ready for a review",
  nearly: "Nearly ready",
  at_risk: "At risk",
  no_payments: "No payments yet",
};

export function bandFor(score: number | null): ReadinessBand {
  if (score === null) return "no_payments";
  if (score >= 90) return "ready";
  if (score >= 70) return "nearly";
  return "at_risk";
}

export function ScoreMeter({
  score,
  band = bandFor(score),
  size = "large",
}: {
  score: number | null;
  band?: ReadinessBand;
  size?: "large" | "small";
}) {
  const label = score === null ? "No readiness score yet" : `Readiness ${score} out of 100`;
  const value = score ?? 0;

  if (size === "small") {
    return (
      <span className={`meter meter-${band}`} role="img" aria-label={label}>
        <span className="meter-track" aria-hidden="true">
          <span className="meter-fill" style={{ width: `${value}%` }} />
        </span>
        <span className="meter-value" aria-hidden="true">
          {score ?? "—"}
        </span>
      </span>
    );
  }

  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  return (
    <svg
      className={`score-ring meter-${band}`}
      viewBox="0 0 128 128"
      width="148"
      height="148"
      role="img"
      aria-label={label}
    >
      <circle cx="64" cy="64" r={radius} className="score-ring-track" />
      <circle
        cx="64"
        cy="64"
        r={radius}
        className="score-ring-fill"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - value / 100)}
        transform="rotate(-90 64 64)"
      />
      <text x="64" y="62" textAnchor="middle" className="score-ring-value">
        {score ?? "—"}
      </text>
      <text x="64" y="84" textAnchor="middle" className="score-ring-unit">
        out of 100
      </text>
    </svg>
  );
}
