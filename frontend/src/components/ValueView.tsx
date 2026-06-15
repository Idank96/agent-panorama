import type { AgentMeta, FeedEntry, ValueRollup, ValueTotals } from "../types";
import { AgentBadge, ScorePill } from "./Feed";

const pct = (rate: number | null): string =>
  rate !== null ? Math.round(rate * 100) + "%" : "-";

const avg = (score: number | null): string =>
  score !== null ? score.toFixed(1) : "-";

interface ValueViewProps {
  entries: FeedEntry[];
  agents: Record<string, AgentMeta>;
  rollups: ValueRollup[];
  totals: ValueTotals | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

/** Center column - the value lens: was the fleet worth it for its users? */
export function ValueView({
  entries,
  agents,
  rollups,
  totals,
  selectedId,
  onSelect,
}: ValueViewProps) {
  const judgedRollups = rollups.filter((r) => r.judged > 0);
  // The manager's job here is finding lost value: worst conversations first.
  const judgedEntries = entries
    .filter((e) => e.value)
    .sort((a, b) => (a.value?.overall_score ?? 0) - (b.value?.overall_score ?? 0));

  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Value</h1>
            <span className="ap-topbar-sub">
              {totals ? `${totals.judged} conversations judged` : "Nothing judged yet"}
            </span>
          </div>
        </div>
      </header>

      <div className="ap-feed-scroll">
        <div className="ap-feed-list">
          {totals && (
            <div className="ap-value-heroes">
              <div className="ap-value-hero">
                <span className="ap-value-hero-label">Avg value score</span>
                <span className="ap-value-hero-num">{avg(totals.avgValueScore)}</span>
                <span className="ap-value-hero-sub">out of 10</span>
              </div>
              <div className="ap-value-hero">
                <span className="ap-value-hero-label">Valuable conversations</span>
                <span className="ap-value-hero-num">{pct(totals.valuableRate)}</span>
                <span className="ap-value-hero-sub">scored 6 or higher</span>
              </div>
              <div className="ap-value-hero is-cost">
                <span className="ap-value-hero-label">Cost per valuable conversation</span>
                <span className="ap-value-hero-num">{totals.costPerValuable ?? "-"}</span>
                <span className="ap-value-hero-sub">
                  {totals.costPerValuable ? "total spend ÷ valuable outcomes" : "enable model_prices for cost"}
                </span>
              </div>
            </div>
          )}

          {judgedRollups.length > 0 && (
            <section className="ap-value-sec">
              <h3>By agent</h3>
              <div className="ap-value-table">
                <div className="ap-value-row is-head">
                  <span>Agent</span>
                  <span>Judged</span>
                  <span>Avg score</span>
                  <span>Valuable</span>
                  <span>Cost / valuable</span>
                </div>
                {judgedRollups.map((r) => (
                  <div className="ap-value-row" key={r.agentKey}>
                    <span className="ap-value-agent">
                      {agents[r.agentKey] ? (
                        <AgentBadge agent={agents[r.agentKey]} />
                      ) : (
                        r.agentName
                      )}
                    </span>
                    <span>{r.judged}</span>
                    <span className="ap-value-strong">{avg(r.avgValueScore)}</span>
                    <span>{pct(r.valuableRate)}</span>
                    <span>{r.costPerValuable ?? "-"}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="ap-value-sec">
            <h3>Conversations, lowest value first</h3>
            {judgedEntries.length === 0 && (
              <div className="ap-empty">
                No judged conversations yet. Add a <code>value:</code> block to
                your config to enable the value layer.
              </div>
            )}
            {judgedEntries.map((entry) => (
              <article
                key={entry.id}
                className={
                  "ap-card ap-value-card" + (selectedId === entry.id ? " is-selected" : "")
                }
                onClick={() => onSelect(entry.id)}
              >
                <div className="ap-card-main">
                  <div className="ap-card-top">
                    {agents[entry.agent] && <AgentBadge agent={agents[entry.agent]} />}
                    <ScorePill score={entry.value?.overall_score ?? 0} />
                  </div>
                  <p className="ap-card-action">{entry.value?.outcome || entry.action}</p>
                  {entry.value && entry.value.value_lost.length > 0 && (
                    <p className="ap-value-lost-hint">
                      {entry.value.value_lost[0]}
                    </p>
                  )}
                </div>
              </article>
            ))}
          </section>
        </div>
      </div>
    </main>
  );
}
