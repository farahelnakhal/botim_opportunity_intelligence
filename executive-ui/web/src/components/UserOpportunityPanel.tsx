// Phase 6/7 — the focused edit experience for a persisted user opportunity
// (details + lifecycle) and its monitoring configuration. Deliberately small
// and consistent with the existing panel styles — no redesign. Committed
// demo/KB opportunities never render these panels (UOPP- records only).
import { useEffect, useState } from "react";
import { useApp } from "../store";
import { userOpportunitiesApi, UserOpportunityError } from "../lib/userOpportunities";
import type { UserMonitoringConfig, UserMonitoringEvent, UserOpportunity } from "../types";
import ActionButton from "./ActionButton";
import Icon from "./Icon";

const splitLines = (v: string) =>
  v.split("\n").map((s) => s.trim()).filter(Boolean).slice(0, 50);
const joinLines = (v: string[] | undefined) => (v ?? []).join("\n");

function Field({ label, value, onChange, multiline = true, placeholder }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  multiline?: boolean;
  placeholder?: string;
}) {
  return (
    <>
      <label>{label}</label>
      {multiline ? (
        <textarea value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input type="text" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      )}
    </>
  );
}

/* ---------------- Details / lifecycle ---------------- */
export function UserOpportunityDetails({ oppId }: { oppId: string }) {
  const { refreshUserOpps, goHome, openReport } = useApp();
  const [record, setRecord] = useState<UserOpportunity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});

  const load = () => {
    userOpportunitiesApi.get(oppId).then((r) => {
      setRecord(r);
      setForm({
        title: r.title,
        product_definition: r.product_definition ?? "",
        problem_statement: r.problem_statement ?? "",
        target_segment: r.target_segment ?? "",
        customer_description: r.customer_description ?? "",
        value_proposition: r.value_proposition ?? "",
        assumptions: joinLines(r.assumptions),
        risks: joinLines(r.risks),
        unknowns: joinLines(r.unknowns),
        next_actions: joinLines(r.next_actions),
      });
    }).catch((e) => setError(String(e instanceof Error ? e.message : e)));
  };
  useEffect(load, [oppId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <div className="panel-wrap"><div className="error-banner">{error}</div></div>;
  if (!record) return <div className="panel-wrap"><div className="skeleton" style={{ height: 160 }} /></div>;

  const set = (key: string) => (v: string) => setForm((f) => ({ ...f, [key]: v }));

  const save = async () => {
    setError(null);
    try {
      const updated = await userOpportunitiesApi.update(record.id, {
        title: form.title,
        product_definition: form.product_definition || null,
        problem_statement: form.problem_statement || null,
        target_segment: form.target_segment || null,
        customer_description: form.customer_description || null,
        value_proposition: form.value_proposition || null,
        assumptions: splitLines(form.assumptions),
        risks: splitLines(form.risks),
        unknowns: splitLines(form.unknowns),
        next_actions: splitLines(form.next_actions),
        version: record.version,
      });
      setRecord(updated);
      await refreshUserOpps();
    } catch (e) {
      setError(e instanceof UserOpportunityError && e.status === 409
        ? "This record changed elsewhere — reload before saving again."
        : `Could not save: ${e instanceof Error ? e.message : e}`);
      throw e;
    }
  };

  const archive = async () => {
    await userOpportunitiesApi.archive(record.id);
    await refreshUserOpps();
    load();
  };
  const restore = async () => {
    await userOpportunitiesApi.restore(record.id);
    await refreshUserOpps();
    load();
  };
  const deleteRecord = async () => {
    const label = record.status === "draft" ? "Permanently delete this draft?"
      : "Permanently delete this archived opportunity? This cannot be undone.";
    if (!window.confirm(label)) return;
    if (record.status === "draft") await userOpportunitiesApi.deleteDraft(record.id);
    else await userOpportunitiesApi.deleteArchived(record.id);
    await refreshUserOpps();
    goHome();
  };

  const archived = record.status === "archived";

  return (
    <div className="panel-wrap" style={{ maxWidth: 680 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Details</div>
          <div className="panel-sub">
            {record.id} · {record.status} · v{record.version} · updated {record.updated_at}
          </div>
        </div>
        <ActionButton className="btn" icon="external" label="Open report" doneLabel="Opened"
          onAct={() => openReport(record.id)} />
      </div>

      <div className="uop-status-note">
        A user-created opportunity draft — unvalidated and unscored. Nothing here is engine
        evidence; the grounded copilot treats these fields as user-provided hypotheses.
      </div>
      {error && <div className="error-banner" style={{ marginBottom: 12 }}>{error}</div>}

      {archived ? (
        <div className="uop-status-note" data-testid="archived-note">
          Archived {record.archived_at} — read-only. Restore it to edit.
        </div>
      ) : (
        <div className="uop-form">
          <Field label="Title" value={form.title} onChange={set("title")} multiline={false} />
          <Field label="Product definition" value={form.product_definition} onChange={set("product_definition")} />
          <Field label="Problem statement" value={form.problem_statement} onChange={set("problem_statement")} />
          <Field label="Target segment" value={form.target_segment} onChange={set("target_segment")} multiline={false} />
          <Field label="Customer description" value={form.customer_description} onChange={set("customer_description")} />
          <Field label="Value proposition" value={form.value_proposition} onChange={set("value_proposition")} />
          <Field label="Assumptions (one per line)" value={form.assumptions} onChange={set("assumptions")} />
          <Field label="Risks (one per line)" value={form.risks} onChange={set("risks")} />
          <Field label="Unknowns (one per line)" value={form.unknowns} onChange={set("unknowns")} />
          <Field label="Recommended next actions (one per line)" value={form.next_actions} onChange={set("next_actions")} />
        </div>
      )}

      <div className="uop-form-actions">
        {!archived && (
          <ActionButton className="btn btn-primary" icon="check-circle" label="Save changes"
            doneLabel="Saved" onAct={save} />
        )}
        {!archived && record.status !== "archived" && (
          <ActionButton className="btn" label="Archive" doneLabel="Archived" onAct={archive}
            title="Hide from the sidebar without deleting" />
        )}
        {archived && (
          <ActionButton className="btn btn-primary" label="Restore" doneLabel="Restored" onAct={restore} />
        )}
        {(record.status === "draft" || archived) && (
          <button type="button" className="btn uop-danger" onClick={deleteRecord}>
            <Icon name="x" size={13} /> Delete {record.status === "draft" ? "draft" : "permanently"}
          </button>
        )}
      </div>
    </div>
  );
}

/* ---------------- Monitoring configuration (Phase 7) ---------------- */
const STATUS_LABEL: Record<string, string> = {
  not_configured: "Not configured",
  never_run: "Configured — awaiting monitoring run",
  active: "Active",
  paused: "Paused",
  error: "Error",
};

export function UserMonitoringPanel({ oppId }: { oppId: string }) {
  const [config, setConfig] = useState<UserMonitoringConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [enabled, setEnabled] = useState(true);
  const [cadence, setCadence] = useState<string>("weekly");
  // Phase R4a — manual runs + recorded events
  const [running, setRunning] = useState(false);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [events, setEvents] = useState<UserMonitoringEvent[]>([]);

  const applyConfig = (c: UserMonitoringConfig) => {
    setConfig(c);
    setEnabled(c.status === "not_configured" ? true : c.enabled);
    setCadence(c.cadence ?? "weekly");
    setForm({
      // prefill: existing values, else the backend's editable suggestions
      topics: joinLines(c.topics?.length ? c.topics : c.suggested_topics),
      keywords: joinLines(c.keywords),
      entities: joinLines(c.entities),
      preferred_domains: joinLines(c.preferred_domains),
      excluded_domains: joinLines(c.excluded_domains),
      geographic_scope: c.geographic_scope ?? "",
      language: c.language ?? "",
      notes: c.notes ?? "",
    });
  };

  const load = () => {
    userOpportunitiesApi.monitoringGet(oppId).then(applyConfig)
      .catch((e) => setError(String(e instanceof Error ? e.message : e)));
    userOpportunitiesApi.monitoringEvents(oppId)
      .then((r) => setEvents(r.events))
      .catch(() => setEvents([])); // events list absent ≠ config broken
  };
  useEffect(load, [oppId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Phase R4a — one manual run; the outcome (incl. failure) is shown verbatim
  const runNow = async () => {
    setRunning(true);
    setRunNote(null);
    try {
      const result = await userOpportunitiesApi.monitoringRun(oppId);
      setRunNote(result.note);
      if (result.config) applyConfig(result.config);
      const refreshed = await userOpportunitiesApi.monitoringEvents(oppId);
      setEvents(refreshed.events);
    } catch (e) {
      setRunNote(String(e instanceof Error ? e.message : e));
    } finally {
      setRunning(false);
    }
  };

  if (error) return <div className="panel-wrap"><div className="error-banner">{error}</div></div>;
  if (!config) return <div className="panel-wrap"><div className="skeleton" style={{ height: 160 }} /></div>;

  const notConfigured = config.status === "not_configured";
  const set = (key: string) => (v: string) => setForm((f) => ({ ...f, [key]: v }));

  const save = async () => {
    const updated = await userOpportunitiesApi.monitoringPut(oppId, {
      enabled,
      cadence: cadence as "manual" | "daily" | "weekly" | "monthly",
      topics: splitLines(form.topics),
      keywords: splitLines(form.keywords),
      entities: splitLines(form.entities),
      preferred_domains: splitLines(form.preferred_domains),
      excluded_domains: splitLines(form.excluded_domains),
      geographic_scope: form.geographic_scope || null,
      language: form.language || null,
      notes: form.notes || null,
    });
    applyConfig(updated);
  };

  return (
    <div className="panel-wrap" style={{ maxWidth: 680 }}>
      <div className="panel-title-row">
        <div>
          <div className="panel-title">Monitoring</div>
          <div className="panel-sub">
            {notConfigured
              ? "Set up monitoring for this opportunity — nothing is enabled without your confirmation"
              : STATUS_LABEL[config.status] ?? config.status}
          </div>
        </div>
      </div>

      {!notConfigured && (
        <dl className="detail-fields" data-testid="monitoring-status">
          <div><dt>Status</dt><dd>{STATUS_LABEL[config.status] ?? config.status}</dd></div>
          <div><dt>Cadence (intended)</dt><dd>{config.cadence}</dd></div>
          <div><dt>Last run</dt><dd>{config.last_run_at ?? "Unavailable — never run"}</dd></div>
          <div><dt>Last error</dt><dd>{config.last_error ?? "None"}</dd></div>
        </dl>
      )}

      <div className="uop-status-note" data-testid="runner-note">
        Manual monitoring runs are available — use “Run monitoring now” to perform one real
        pass (requires a configured search provider; results and any failures are recorded
        honestly). There is no scheduler yet, so the cadence below remains stored intent
        rather than an automatic schedule.
      </div>

      <div className="uop-form">
        <label>Enabled</label>
        <button type="button" className={`switch${enabled ? " on" : ""}`}
          aria-label="Enable monitoring" onClick={() => setEnabled((v) => !v)} />
        <label>Cadence (stored as intended configuration — no scheduler runs yet)</label>
        <select value={cadence} onChange={(e) => setCadence(e.target.value)}>
          <option value="manual">manual</option>
          <option value="daily">daily</option>
          <option value="weekly">weekly</option>
          <option value="monthly">monthly</option>
        </select>
        <Field label="Topics (one per line — editable suggestions prefilled)" value={form.topics} onChange={set("topics")} />
        <Field label="Keywords (one per line)" value={form.keywords} onChange={set("keywords")} />
        <Field label="Entities / competitors (one per line)" value={form.entities} onChange={set("entities")} />
        <Field label="Preferred domains (one per line)" value={form.preferred_domains} onChange={set("preferred_domains")} />
        <Field label="Excluded domains (one per line)" value={form.excluded_domains} onChange={set("excluded_domains")} />
        <Field label="Geographic scope" value={form.geographic_scope} onChange={set("geographic_scope")} multiline={false} placeholder="e.g. UAE" />
        <Field label="Language" value={form.language} onChange={set("language")} multiline={false} placeholder="e.g. en, ar" />
        <Field label="Notes" value={form.notes} onChange={set("notes")} />
      </div>

      <div className="uop-form-actions">
        <ActionButton className="btn btn-primary" icon="check-circle"
          label={notConfigured ? "Set up monitoring" : "Save configuration"}
          doneLabel="Saved" onAct={save} />
        {!notConfigured && config.enabled && (
          <ActionButton className="btn" label="Pause" doneLabel="Paused"
            onAct={async () => applyConfig(await userOpportunitiesApi.monitoringPause(oppId))} />
        )}
        {!notConfigured && !config.enabled && (
          <ActionButton className="btn" label="Resume" doneLabel="Resumed"
            onAct={async () => applyConfig(await userOpportunitiesApi.monitoringResume(oppId))} />
        )}
        {!notConfigured && (
          <button type="button" className="btn uop-danger"
            onClick={async () => {
              if (!window.confirm("Remove this monitoring configuration?")) return;
              await userOpportunitiesApi.monitoringDelete(oppId);
              load();
            }}>
            <Icon name="x" size={13} /> Remove configuration
          </button>
        )}
        {!notConfigured && (
          <button type="button" className="btn" disabled={running || !config.enabled}
            onClick={runNow}
            title={config.enabled
              ? "Run one manual monitoring pass now (requires a configured search provider)"
              : "Resume monitoring before running"}>
            {running ? "Running…" : "Run monitoring now"}
          </button>
        )}
      </div>

      {runNote && (
        <div className="banner-note" data-testid="monitoring-run-note" style={{ marginTop: 10 }}>
          <Icon name={runNote.startsWith("Monitoring run failed") ? "alert" : "check-circle"} />
          <span>{runNote}</span>
        </div>
      )}

      {!notConfigured && (
        <div className="uop-mon-events">
          <h4>Detected developments</h4>
          {events.length === 0 ? (
            <p className="empty-note" data-testid="monitoring-no-events">
              {config.last_run_at
                ? "No new developments have been detected yet."
                : "No events — monitoring has not run yet."}
            </p>
          ) : (
            events.map((e) => (
              <div className="research-source" key={e.id} data-testid="monitoring-event">
                <div className="research-source-main">
                  <div className="research-source-title">{e.title || e.domain}</div>
                  <div className="research-source-meta">
                    {e.domain}
                    {e.published_at ? ` · published ${e.published_at.slice(0, 10)}` : ""}
                    {" · detected "}{e.detected_at.slice(0, 10)}
                    {" · run "}{e.research_run_id}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
