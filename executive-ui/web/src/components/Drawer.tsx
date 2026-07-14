import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../store";
import { confidenceLabel, humanFactorKey, tagClass, tagLabel } from "../lib/format";
import { humanize } from "../lib/labels";
import type { CommercialModel } from "../types";
import Icon from "./Icon";
import ScoreRing from "./ScoreRing";

function Section({ title, defaultOpen = false, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="dsec">
      <div className="dsec-head" onClick={() => setOpen((o) => !o)}>
        <div className="dsec-title">{title}</div>
        <Icon name="chevron" className={`icon chev${open ? " open" : ""}`} />
      </div>
      {open && <div className="dsec-body">{children}</div>}
    </div>
  );
}

export default function Drawer() {
  const { drawerOppId, closeDrawer, projects, generated, overview, openDetail } = useApp();
  const opp = [...generated, ...projects].find((p) => p.id === drawerOppId) ?? null;
  const [comm, setComm] = useState<CommercialModel | null>(null);

  useEffect(() => {
    if (drawerOppId) api.commercial(drawerOppId).then(setComm);
    else setComm(null);
  }, [drawerOppId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeDrawer();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeDrawer]);

  const show = !!opp;
  const assumptions = overview?.assumptions.filter((a) => a.opportunity_id === drawerOppId) ?? [];
  const weak = assumptions.filter((a) => a.status !== "supported").slice(0, 6);
  const strongEv = opp?.strongest_evidence ?? [];

  return (
    <>
      <div className={`drawer-backdrop${show ? " show" : ""}${show ? "" : " hidden"}`} onClick={closeDrawer} />
      <aside className={`drawer${show ? " show" : ""}${show ? "" : " hidden"}`}>
        {opp && (
          <>
            <div className="drawer-header">
              <div>
                <div className="drawer-header-title">{opp.name}</div>
                {opp.generated && (
                  <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>AI-generated · unvalidated hypothesis</div>
                )}
              </div>
              <button className="drawer-close" onClick={closeDrawer}><Icon name="x" /></button>
            </div>

            <div className="drawer-score-row">
              <ScoreRing raw={opp.raw_score} max={opp.raw_max} />
              <div>
                <span className={`tag ${tagClass(opp.classification)}`}>{tagLabel(opp.classification)}</span>
                <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 6 }}>
                  Confidence <b style={{ color: "var(--text-secondary)" }}>{confidenceLabel(opp.confidence)}</b>
                  {opp.raw_score != null && <> · Composite <b style={{ color: "var(--text-secondary)" }}>{opp.composite}</b></>}
                  {" "}· <b style={{ color: "var(--text-secondary)" }}>{opp.assumption_count}</b> assumptions
                </div>
              </div>
            </div>

            <div className="drawer-body">
              {opp.hypothesis && opp.hypothesis !== "—" && (
                <Section title="Summary" defaultOpen>{humanize(opp.hypothesis)}</Section>
              )}
              {opp.jtbd && opp.jtbd !== "—" && (
                <Section title="Job to be done" defaultOpen>{humanize(opp.jtbd)}</Section>
              )}
              {opp.next_action && opp.next_action !== "—" && (
                <Section title="Current recommendation" defaultOpen>{humanize(opp.next_action)}</Section>
              )}

              {strongEv.length > 0 && (
                <Section title="Strongest supporting evidence">
                  <ul className="evidence-list">
                    {strongEv.map((e) => (
                      <li key={e.ev_id}>
                        <span className="dot" />
                        <button type="button" className="evidence-list-link" onClick={() => openDetail("evidence", e.ev_id)}>
                          {e.title !== "—" ? e.title : "Customer-evidence record"} <span className="source-tag">strength {String(e.strength)}, {confidenceLabel(e.confidence)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {opp.contradictory_evidence && opp.contradictory_evidence !== "—" && (
                <Section title="Contradictory evidence">{humanize(opp.contradictory_evidence)}</Section>
              )}

              {weak.length > 0 && (
                <Section title="Weakest assumptions">
                  <ul className="evidence-list">
                    {weak.map((a, i) => (
                      <li key={i}>
                        <span className="dot weak" />
                        <button
                          type="button"
                          className="evidence-list-link"
                          onClick={() => openDetail("assumption", `${a.opportunity_id}::${a.factor_key}`)}
                        >
                          {humanize(a.text)} <span className="source-tag">— {a.status}, importance {a.decision_importance}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}

              {comm && (
                <Section title="Commercial outlook">
                  {(() => {
                    const base = comm.cases.base;
                    if (!base) return "No base case available.";
                    return (
                      <>
                        Base case: contribution {comm.currency} {base.contribution.toLocaleString()} per merchant/month
                        ({base.contribution_pct}% of revenue);
                        {base.breakeven_merchants != null ? ` break-even around ${base.breakeven_merchants} merchants.` : " no break-even at these unit economics."}
                        <p className="source-tag" style={{ marginTop: 8 }}>{comm.note}</p>
                      </>
                    );
                  })()}
                </Section>
              )}

              {opp.factors.length > 0 && (
                <Section title="Detailed score (17 dimensions)" defaultOpen>
                  <div className="score-bars">
                    {opp.factors.map((f) => (
                      <div className="score-bar-row" key={f.key}>
                        <div className="score-bar-label">{humanFactorKey(f.key)}{f.assumption && <span className="source-tag"> (A)</span>}</div>
                        <div className="score-bar-track"><div className={`score-bar-fill${f.assumption ? " assume" : ""}`} style={{ width: `${(f.score / 5) * 100}%` }} /></div>
                        <div className="score-bar-val">{f.score}/5</div>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              <Section title="History">
                {opp.impact_history.length > 0 ? (
                  opp.impact_history.map((h: any, i) => (
                    <div className="history-item" key={i}>
                      <span className="history-dot" />
                      <span className="history-date">{String(h.timestamp || "").slice(0, 10)}</span>
                      <span className="history-text">{h.kind || "applied"}: raw {h.raw_score_prev}→{h.raw_score_new}, approved by {h.approved_by}</span>
                    </div>
                  ))
                ) : opp.score_history.length > 0 ? (
                  opp.score_history.map((h, i) => (
                    <div className="history-item" key={i}>
                      <span className="history-dot" />
                      <span className="history-date">{h.date}</span>
                      <span className="history-text">{h.subject}</span>
                    </div>
                  ))
                ) : (
                  <span className="source-tag">No approved impact transactions recorded.</span>
                )}
              </Section>

              <p className="source-tag" style={{ display: "block", marginTop: 16 }}>
                No product or build decision has been made.
              </p>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
