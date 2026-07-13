import { RING_CIRCUMFERENCE, ringOffset, scorePct } from "../lib/format";

// Visual proportion of the engine's raw/max — not an invented 0–100 score.
export default function ScoreRing({
  raw,
  max,
  size = 64,
}: {
  raw: number | null;
  max: number;
  size?: number;
}) {
  const pct = scorePct(raw, max);
  return (
    <div className="opp-score-ring" style={{ width: size, height: size }}>
      <svg viewBox="0 0 64 64" width={size} height={size}>
        <circle className="ring-bg" cx="32" cy="32" r="27" />
        <circle
          className="ring-fg"
          cx="32"
          cy="32"
          r="27"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={ringOffset(pct)}
        />
      </svg>
      <div className="opp-score-num">
        {raw == null ? "—" : raw}
        {raw != null && <small>/{max}</small>}
      </div>
    </div>
  );
}
