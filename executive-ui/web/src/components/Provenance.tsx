// Phase 4 — small shared provenance widgets: the freshness badge (displays
// the backend-computed status, never re-derives it) and the safe external
// source link (http(s) only; anything else renders honest text, never an
// anchor). Used by the evidence DetailDrawer, chat citations, and the web
// report page so wording and safety rules cannot drift apart.
import { safeExternalUrl } from "../lib/safeUrl";
import type { FreshnessStatus } from "../types";
import Icon from "./Icon";

const FRESHNESS_LABEL: Record<FreshnessStatus, string> = {
  fresh: "Fresh",
  aging: "Aging",
  stale: "Stale",
  unknown: "Freshness unknown",
};

export function FreshnessBadge({ status }: { status?: FreshnessStatus | null }) {
  const s: FreshnessStatus = status && status in FRESHNESS_LABEL ? status : "unknown";
  return (
    <span className={`freshness-badge ${s}`} data-testid="freshness-badge">
      {s === "stale" && <Icon name="alert" size={11} />}
      {FRESHNESS_LABEL[s]}
    </span>
  );
}

export function ExternalSourceLink({
  url,
  label,
}: {
  url?: string | null;
  label?: string | null;
}) {
  const safe = safeExternalUrl(url);
  if (!safe) {
    return (
      <p className="no-source-note" data-testid="no-source-note">
        {url
          ? "The recorded source reference is not a safe web address, so no link is shown."
          : "This is an internal repository record and has no external source URL."}
      </p>
    );
  }
  return (
    <a
      className="external-source-link"
      href={safe}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`Open original source${label ? `: ${label}` : ""} (opens in a new tab)`}
      data-testid="external-source-link"
    >
      <Icon name="external" size={13} /> Open original source{label ? ` — ${label}` : ""}
    </a>
  );
}
