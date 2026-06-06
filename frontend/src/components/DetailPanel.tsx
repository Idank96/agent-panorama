import type {
  AgentMeta,
  Decision,
  FeedEntry,
  Status,
  ValueJudgment,
} from "../types";
import { STATUS } from "../data/agents";
import { ScorePill } from "./Feed";
import {
  IconAlert,
  IconBolt,
  IconCheck,
  IconClock,
  IconShield,
  IconX,
} from "../icons";

interface DetailPanelProps {
  entry: FeedEntry | null;
  agent: AgentMeta | null;
  decision?: Decision;
  onDecision: (id: string, decision: Decision | null) => void;
}

const effectiveStatus = (status: Status, decision?: Decision): Status =>
  decision === "approved"
    ? "completed"
    : decision === "rejected"
      ? "failed"
      : status;

/** The value layer's verdict: scores, value delivered/lost, fixes, criteria. */
function ValueSection({ value }: { value: ValueJudgment }) {
  const subScores: [string, number][] = [
    ["Goal", value.goal_completion],
    ["Quality", value.response_quality],
    ["Efficiency", value.efficiency],
    ...Object.entries(value.custom_scores),
  ];
  return (
    <section className="ap-detail-sec">
      <h3>Value</h3>
      <div className="ap-value-verdict">
        <div className="ap-value-verdict-top">
          <ScorePill score={value.overall_score} />
          <span className="ap-value-outcome">{value.outcome}</span>
        </div>
        <div className="ap-value-subscores">
          {subScores.map(([label, score]) => (
            <span className="ap-value-subscore" key={label}>
              {label} <b>{score}</b>
            </span>
          ))}
        </div>
        {value.value_delivered.length > 0 && (
          <ul className="ap-value-list is-delivered">
            {value.value_delivered.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        {value.value_lost.length > 0 && (
          <ul className="ap-value-list is-lost">
            {value.value_lost.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        {value.recommended_fixes.length > 0 && (
          <ul className="ap-value-list is-fixes">
            {value.recommended_fixes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        )}
        {Object.keys(value.criteria_verdicts).length > 0 && (
          <dl className="ap-kv ap-value-criteria">
            {Object.entries(value.criteria_verdicts).map(([criterion, met]) => (
              <div className="ap-kv-row" key={criterion}>
                <dt>{criterion}</dt>
                <dd className={met ? "is-met" : "is-unmet"}>
                  {met ? "Met" : "Not met"}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <p className="ap-value-rationale">{value.rationale}</p>
      </div>
    </section>
  );
}

/** Right panel — expanded detail of the selected activity. */
export function DetailPanel({
  entry,
  agent,
  decision,
  onDecision,
}: DetailPanelProps) {
  if (!entry || !agent) {
    return (
      <aside className="ap-detail ap-detail-empty">
        <div className="ap-detail-empty-inner">
          <span className="ap-detail-empty-mark">
            <i />
            <i />
            <i />
            <i />
          </span>
          <p>Select an activity to inspect the full record.</p>
        </div>
      </aside>
    );
  }

  const accent = agent.accent;
  const effStatus = effectiveStatus(entry.status, decision);
  const sMeta = STATUS[effStatus];

  return (
    <aside className="ap-detail" key={entry.id}>
      <div className="ap-detail-hd" style={{ background: agent.tint }}>
        <div className="ap-detail-hd-row">
          <span
            className="ap-badge"
            style={{ color: accent, background: "rgba(255,255,255,.6)" }}
          >
            <span className="ap-badge-mark" style={{ background: accent }}>
              {agent.short}
            </span>
            {agent.name}
          </span>
          <span className={"ap-pill ap-pill-" + sMeta.kind}>{sMeta.label}</span>
        </div>
        <p className="ap-detail-action">{entry.action}</p>
        <div className="ap-detail-time">
          <IconClock size={13} />
          {entry.fullTime}
        </div>
      </div>

      <div className="ap-detail-scroll">
        <p className="ap-detail-summary">{entry.summary}</p>

        <section className="ap-detail-sec">
          <h3>Details</h3>
          <dl className="ap-kv">
            {entry.facts.map(([k, v]) => (
              <div className="ap-kv-row" key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </section>

        {entry.policy && (
          <section className="ap-detail-sec">
            <h3>Policy applied</h3>
            <div className="ap-policy">
              <div className="ap-policy-rule">
                <IconShield size={15} style={{ color: accent }} />
                <span>{entry.policy.rule}</span>
              </div>
              <p className="ap-policy-detail">{entry.policy.detail}</p>
            </div>
          </section>
        )}

        {entry.value && <ValueSection value={entry.value} />}

        <section className="ap-detail-sec">
          <h3>Cost</h3>
          <div className="ap-cost">
            <div className="ap-cost-item">
              <span className="ap-cost-label">
                <IconBolt size={13} /> Tokens
              </span>
              <span className="ap-cost-val">
                {entry.tokens.used.toLocaleString()}
              </span>
            </div>
            {entry.tokens.cost !== null && (
              <div className="ap-cost-item">
                <span className="ap-cost-label">Est. cost</span>
                <span className="ap-cost-val">{entry.tokens.cost}</span>
              </div>
            )}
          </div>
        </section>
      </div>

      {entry.status === "pending" && (
        <div className="ap-detail-foot">
          {!decision ? (
            <>
              <div className="ap-detail-foot-note">
                <IconAlert size={14} />
                Needs your approval before the agent continues.
              </div>
              <div className="ap-detail-foot-btns">
                <button
                  className="ap-btn-lg ap-btn-reject"
                  onClick={() => onDecision(entry.id, "rejected")}
                >
                  <IconX size={15} /> Reject
                </button>
                <button
                  className="ap-btn-lg ap-btn-approve-solid"
                  style={{ background: accent }}
                  onClick={() => onDecision(entry.id, "approved")}
                >
                  <IconCheck size={15} /> Approve
                </button>
              </div>
            </>
          ) : (
            <div className={"ap-resolved ap-resolved-" + decision}>
              {decision === "approved" ? (
                <IconCheck size={15} />
              ) : (
                <IconX size={15} />
              )}
              {decision === "approved"
                ? "You approved this action."
                : "You rejected this action."}
              <button
                className="ap-undo"
                onClick={() => onDecision(entry.id, null)}
              >
                Undo
              </button>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}
