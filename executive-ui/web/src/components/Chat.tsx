import { useEffect, useRef, useState } from "react";
import { useApp, type Message } from "../store";
import type { ChatBlock } from "../types";
import Icon from "./Icon";
import {
  Banner, BriefEnvelopeCard, CalibrationCard, CommercialModelCard, DecisionJournalEntry,
  EvidenceCard, ExecutiveSummaryCard, ExperimentCard, FeedItemCard, MonitoringAlertCard,
  OpportunityCard, OpportunityMini, Scorecard,
} from "./cards";

/* ---------------- progress timeline ---------------- */
function Timeline({ stages, done }: { stages: string[]; done: boolean }) {
  if (!stages.length) return null;
  return (
    <div className="timeline">
      {stages.map((s, i) => {
        const last = i === stages.length - 1;
        const complete = done || !last;
        return (
          <div className={`timeline-step${complete ? " done" : ""}`} key={i} style={{ animationDelay: `${i * 0.12}s` }}>
            {complete ? (
              <span className="step-check"><Icon name="check" /></span>
            ) : (
              <span className="step-spin" />
            )}
            {s}
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- block renderer with grouping ---------------- */
function Blocks({ blocks }: { blocks: ChatBlock[] }) {
  const out: JSX.Element[] = [];
  let i = 0;
  while (i < blocks.length) {
    const b = blocks[i];
    // group consecutive opportunity blocks into a lead card + mini row
    if (b.type === "opportunity") {
      const run: ChatBlock[] = [];
      while (i < blocks.length && blocks[i].type === "opportunity") run.push(blocks[i++]);
      out.push(
        <div className="opp-grid" key={`opp-${i}`}>
          {run[0].opportunity && <OpportunityCard opp={run[0].opportunity} />}
          {run.length > 1 && (
            <div className="opp-mini-row">
              {run.slice(1).map((r) => r.opportunity && <OpportunityMini key={r.opportunity.id} opp={r.opportunity} />)}
            </div>
          )}
        </div>,
      );
      continue;
    }
    if (b.type === "monitoring_alert" || b.type === "feed_item") {
      const run: ChatBlock[] = [];
      while (i < blocks.length && (blocks[i].type === "monitoring_alert" || blocks[i].type === "feed_item")) run.push(blocks[i++]);
      out.push(
        <div key={`mon-${i}`}>
          {run.map((r, k) => r.type === "monitoring_alert"
            ? <MonitoringAlertCard key={k} data={r.data} />
            : <FeedItemCard key={k} data={r.data} />)}
        </div>,
      );
      continue;
    }
    out.push(<div key={`b-${i}`}>{renderOne(b)}</div>);
    i++;
  }
  return <>{out}</>;
}

function renderOne(b: ChatBlock): JSX.Element | null {
  switch (b.type) {
    case "scorecard": return b.opportunity ? <Scorecard opp={b.opportunity} /> : null;
    case "executive_summary": return b.opportunity ? <ExecutiveSummaryCard opp={b.opportunity} /> : null;
    case "brief_envelope": return <BriefEnvelopeCard data={b.data} />;
    case "commercial_model": return <CommercialModelCard data={b.data} />;
    case "experiment": return <ExperimentCard data={b.data} />;
    case "calibration": return <CalibrationCard data={b.data} />;
    case "decision_journal": return <DecisionJournalEntry data={b.data} />;
    case "evidence": return <EvidenceCard data={b.data} />;
    case "banner": return <Banner text={b.text || ""} />;
    case "empty": return <div className="empty-state"><div className="empty-state-title">Nothing to show</div>{b.text}</div>;
    default: return null;
  }
}

/* ---------------- message ---------------- */
function MessageView({ m }: { m: Message }) {
  if (m.role === "user") {
    return (
      <div className="msg msg-user">
        <div className="msg-role">You</div>
        <div className="msg-bubble">{m.text}</div>
      </div>
    );
  }
  return (
    <div className="msg msg-assistant">
      <div className="msg-role">BOTIM</div>
      <Timeline stages={m.stages ?? []} done={!m.streaming} />
      {m.text && (
        <div className="msg-assistant-body">
          <p>{m.text}{m.streaming && <span className="stream-caret" />}</p>
        </div>
      )}
      {m.blocks && <Blocks blocks={m.blocks} />}
    </div>
  );
}

/* ---------------- input ---------------- */
function ChatInput({ onSend }: { onSend: (t: string) => void }) {
  const [val, setVal] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const submit = () => {
    const t = val.trim();
    if (!t) return;
    onSend(t);
    setVal("");
    if (ref.current) ref.current.style.height = "auto";
  };
  return (
    <div className="chat-input-dock">
      <div className="chat-input-inner">
        <div className="chat-input-card">
          <textarea
            ref={ref}
            rows={1}
            value={val}
            placeholder="Ask a follow-up, request a brief, or point BOTIM at new evidence…"
            onChange={(e) => {
              setVal(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button className="icon-btn" title="Attach"><Icon name="paperclip" /></button>
          <button className="send-btn" style={{ margin: 4 }} disabled={!val.trim()} onClick={submit}>
            <Icon name="send" size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------- chat view ---------------- */
export default function Chat({ projectId }: { projectId: string }) {
  const { conversations, send } = useApp();
  const msgs = conversations[projectId] ?? [];
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  return (
    <div className="tab-panel" style={{ display: "flex", flexDirection: "column" }}>
      <div className="chat-scroll" style={{ flex: 1 }}>
        {msgs.length === 0 && (
          <div className="empty-state" style={{ paddingTop: 80 }}>
            <Icon name="message" className="icon" />
            <div className="empty-state-title">Start the conversation</div>
            Ask about an opportunity, its commercial model, evidence, experiments, or what changed this week.
          </div>
        )}
        {msgs.map((m) => <MessageView key={m.id} m={m} />)}
        <div ref={endRef} />
      </div>
      <ChatInput onSend={(t) => send(t, projectId)} />
    </div>
  );
}
