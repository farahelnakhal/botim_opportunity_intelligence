import { useRef, useState } from "react";
import { useApp } from "../store";
import { tagLabel } from "../lib/format";
import Icon from "./Icon";
import AssistantAnswer, { fromCopilotResult } from "./AssistantAnswer";
import type { CopilotChatResult } from "../types";

const EXAMPLE_PROMPTS = [
  "Invoice financing for UAE logistics SMEs",
  "Pharmacy working-capital lending in Saudi Arabia",
  "Instant settlement for grocery merchants in Egypt",
  "Cross-border payroll for GCC construction firms",
  "BNPL for private-school tuition in the UAE",
  "Embedded insurance for gig-economy drivers",
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const { projects, userProjects, appMode, openProject, analyzeNew } = useApp();
  const [val, setVal] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  // Phase 3 — a message that ISN'T a genuine new-product idea (a greeting, a
  // monitoring question, a methodology question, …) never creates a sidebar
  // opportunity stub or navigates away from Home; the reply renders inline,
  // right here, exactly like the rest of the app renders a copilot answer.
  const [quick, setQuick] = useState<{ id: number; prompt: string; result: CopilotChatResult }[]>([]);
  const quickId = useRef(0);

  const submit = async (text?: string) => {
    const t = (text ?? val).trim();
    if (!t) return;
    setVal("");
    const result = await analyzeNew(t);
    if (result.answerType !== "new_opportunity_analysis") {
      setQuick((q) => [...q, { id: ++quickId.current, prompt: t, result }]);
    }
    // A genuine new-product idea: analyzeNew already navigated to the new
    // project's chat, so this component is about to unmount — nothing more to do.
  };

  return (
    <section className="view" id="view-home">
      <div className="home-wrap">
        <div className="home-greeting">{greeting()}</div>
        <div className="home-sub">Describe any market or product idea — I'll run a fresh opportunity analysis.</div>

        <div className="home-input-card">
          <textarea
            rows={1}
            value={val}
            placeholder="e.g. Invoice financing for UAE logistics SMEs waiting 45 days to get paid…"
            onChange={(e) => {
              setVal(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="home-input-actions">
            <div className="input-tools">
              <button
                className="icon-btn"
                title="Note file names only — files are not uploaded to or read by the analysis engine yet"
                onClick={() => fileRef.current?.click()}
              >
                <Icon name="paperclip" />
              </button>
              <input
                ref={fileRef} type="file" multiple hidden
                onChange={(e) => {
                  const names = Array.from(e.target.files ?? []).map((f) => f.name);
                  if (names.length) {
                    setVal((v) => `${v}${v ? " " : ""}[file names noted, not uploaded or analyzed: ${names.join(", ")}] `);
                  }
                  e.target.value = "";
                }}
              />
            </div>
            <button className="send-btn" disabled={!val.trim()} onClick={() => submit()}>
              <Icon name="send" size={15} />
            </button>
          </div>
        </div>

        <div className="example-prompts">
          {EXAMPLE_PROMPTS.map((p) => (
            <button className="prompt-pill" key={p} onClick={() => submit(p)}>{p}</button>
          ))}
        </div>

        {quick.length > 0 && (
          <div className="home-quick-replies">
            {quick.map((q) => (
              <div className="msg msg-assistant" key={q.id}>
                <div className="msg-role">BOTIM</div>
                <AssistantAnswer data={fromCopilotResult(q.result)} />
              </div>
            ))}
          </div>
        )}

        {userProjects.length > 0 && (
          <>
            <div className="home-recent-label">Your opportunities</div>
            <div className="recent-grid">
              {userProjects.map((p) => (
                <button className="recent-card" key={p.id} onClick={() => openProject(p.id)}>
                  <div className="recent-card-top"><span className="status-dot review" /></div>
                  <div className="recent-card-title">{p.name}</div>
                  <div className="recent-card-meta">{p.classification_label}</div>
                </button>
              ))}
            </div>
          </>
        )}

        {/* Phase 5 — the committed corpus renders only in demo/test mode,
            clearly labelled; normal mode gets a clean invite instead. */}
        {projects.length > 0 && (
          <>
            <div className="home-recent-label">
              Demo opportunities <span className="chip">demo data</span>
            </div>
            <div className="recent-grid">
              {projects.map((p) => {
                const dot = p.classification === "reject" ? "paused"
                  : p.classification === "strong" || p.classification === "promising" ? "active" : "review";
                return (
                  <button className="recent-card" key={p.id} onClick={() => openProject(p.id)}>
                    <div className="recent-card-top"><span className={`status-dot ${dot}`} /></div>
                    <div className="recent-card-title">{p.name}</div>
                    <div className="recent-card-meta">{tagLabel(p.classification)}</div>
                  </button>
                );
              })}
            </div>
          </>
        )}

        {appMode === "normal" && projects.length === 0 && userProjects.length === 0 && (
          <div className="empty-state" style={{ paddingTop: 28 }} data-testid="home-empty-invite">
            <Icon name="star" className="icon" />
            <div className="empty-state-title">No opportunities yet</div>
            Describe your first product idea above — the grounded analysis can then be saved
            as your first opportunity.
          </div>
        )}
      </div>
    </section>
  );
}
