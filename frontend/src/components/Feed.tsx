import type { AgentMeta, Decision, FeedEntry, Status } from "../types";
import { STATUS } from "../data/agents";
import {
  IconCalendar,
  IconCheck,
  IconChevron,
  IconExport,
  IconSearch,
  IconX,
} from "../icons";

export function StatusPill({ status }: { status: Status }) {
  const meta = STATUS[status];
  return <span className={"ap-pill ap-pill-" + meta.kind}>{meta.label}</span>;
}

/** Score band → pill kind, aligned with the backend's "valuable" threshold (6). */
export const scoreKind = (score: number): Status =>
  score >= 6 ? "completed" : score >= 4 ? "pending" : "failed";

/** Compact 0-10 value-score pill shown on judged conversations. */
export function ScorePill({ score }: { score: number }) {
  return (
    <span className={"ap-pill ap-pill-" + scoreKind(score)}>{score}/10</span>
  );
}

export function AgentBadge({ agent }: { agent?: AgentMeta }) {
  if (!agent) return null;
  return (
    <span
      className="ap-badge"
      style={{ color: agent.accent, background: agent.tint }}
    >
      <span className="ap-badge-mark" style={{ background: agent.accent }}>
        {agent.short}
      </span>
      {agent.name}
    </span>
  );
}

const IconChevronInline = () => (
  <svg
    width="11"
    height="11"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    style={{ opacity: 0.5 }}
  >
    <path d="M6 9l6 6 6-6" />
  </svg>
);

const effectiveStatus = (status: Status, decision?: Decision): Status =>
  decision === "approved"
    ? "completed"
    : decision === "rejected"
      ? "failed"
      : status;

interface FeedCardProps {
  entry: FeedEntry;
  agent: AgentMeta;
  selected: boolean;
  onSelect: (id: string) => void;
  decision?: Decision;
  onDecision: (id: string, decision: Decision | null) => void;
}

export function FeedCard({
  entry,
  agent,
  selected,
  onSelect,
  decision,
  onDecision,
}: FeedCardProps) {
  // Decision overrides the on-card status once the manager has acted.
  const effStatus = effectiveStatus(entry.status, decision);

  return (
    <article
      className={"ap-card" + (selected ? " is-selected" : "")}
      style={{ borderLeft: "1px solid var(--ap-border)" }}
      onClick={() => onSelect(entry.id)}
    >
      <div className="ap-card-main">
        <div className="ap-card-top">
          <AgentBadge agent={agent} />
          <span className="ap-card-time">{entry.time}</span>
        </div>

        <p className="ap-card-action">{entry.action}</p>

        <div className="ap-card-foot">
          <StatusPill status={effStatus} />
          {entry.value && <ScorePill score={entry.value.overall_score} />}

          {entry.status === "pending" && !decision ? (
            <div className="ap-actions" onClick={(e) => e.stopPropagation()}>
              <button
                className="ap-btn ap-btn-approve"
                onClick={() => onDecision(entry.id, "approved")}
              >
                <IconCheck size={13} /> Approve
              </button>
              <button
                className="ap-btn ap-btn-reject"
                onClick={() => onDecision(entry.id, "rejected")}
              >
                <IconX size={13} /> Reject
              </button>
            </div>
          ) : (
            <button
              className="ap-details-toggle"
              onClick={(e) => {
                e.stopPropagation();
                onSelect(entry.id);
              }}
            >
              Details
              <IconChevron size={13} className={selected ? "rot" : ""} />
            </button>
          )}
        </div>

        {decision && (
          <div className={"ap-decision-note ap-decision-" + decision}>
            {decision === "approved"
              ? "Approved by you · agent proceeding"
              : "Rejected by you · agent halted"}
          </div>
        )}
      </div>
    </article>
  );
}

interface FeedProps {
  entries: FeedEntry[];
  agents: Record<string, AgentMeta>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  decisions: Record<string, Decision>;
  onDecision: (id: string, decision: Decision | null) => void;
  query: string;
  setQuery: (q: string) => void;
  filterName: string | null;
}

/** Center column — top bar + chronological activity feed. */
export function Feed({
  entries,
  agents,
  selectedId,
  onSelect,
  decisions,
  onDecision,
  query,
  setQuery,
  filterName,
}: FeedProps) {
  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Activity Feed</h1>
            <span className="ap-topbar-sub">
              {filterName ? filterName + " · " : ""}
              {entries.length} events today
            </span>
          </div>
          <div className="ap-topbar-tools">
            <button className="ap-daterange">
              <IconCalendar size={15} />
              May 31, 2026
              <IconChevronInline />
            </button>
            <div className="ap-searchbox">
              <IconSearch size={15} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search activity…"
              />
            </div>
            <button className="ap-export">
              <IconExport size={15} />
              Export Report
            </button>
          </div>
        </div>
      </header>

      <div className="ap-feed-scroll">
        <div className="ap-feed-list">
          {entries.length === 0 && (
            <div className="ap-empty">No activity matches “{query}”.</div>
          )}
          {entries.map((entry) => (
            <FeedCard
              key={entry.id}
              entry={entry}
              agent={agents[entry.agent]}
              selected={selectedId === entry.id}
              onSelect={onSelect}
              decision={decisions[entry.id]}
              onDecision={onDecision}
            />
          ))}
        </div>
      </div>
    </main>
  );
}
