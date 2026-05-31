import type { AgentMeta, FeedEntry, Outcome, Status } from "../types";
import { AGENTS, resolveAgent } from "../data/agents";
import { demoFeed } from "../data/demoFeed";

export interface BackendFeedItem {
  run_id: string;
  agent_name: string;
  agent_key: string;
  action: string;
  outcome: Outcome;
  timestamp: string | null;
  retry_count: number;
  anomaly_count: number;
  tokens: number;
  cost_usd: number | null;
  summary: string;
  facts: [string, string][];
  anomalies: string[];
}

export interface BackendReport {
  generated_at: string;
  time_range: { start: string | null; end: string | null };
  totals: { runs: number; steps: number; tokens: number; cost_usd: number | null };
  feed: BackendFeedItem[];
  rollups: unknown[];
  decision_log: unknown[];
}

export interface LoadedFeed {
  entries: FeedEntry[];
  agents: Record<string, AgentMeta>;
}

const OUTCOME_TO_STATUS: Record<Outcome, Status> = {
  success: "completed",
  "human-escalated": "pending",
  failure: "failed",
  unknown: "completed",
};

/** Map a backend outcome string to a frontend feed status. */
export const outcomeToStatus = (outcome: Outcome): Status =>
  OUTCOME_TO_STATUS[outcome] ?? "completed";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Human relative time ("2m ago"); falls back to the raw ISO string on parse failure. */
export const relativeTime = (iso: string | null, now: number = Date.now()): string => {
  if (!iso) return "—";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  const diff = Math.max(0, now - ts);
  if (diff < MINUTE) return "just now";
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m ago`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h ago`;
  return `${Math.floor(diff / DAY)}d ago`;
};

/** Format a full timestamp for the detail header; falls back to the raw ISO. */
export const formatFullTime = (iso: string | null): string => {
  if (!iso) return "—";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return iso;
  return new Date(ts).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

const formatCost = (cost: number | null): string | null =>
  cost !== null && cost !== undefined ? "$" + cost.toFixed(4) : null;

/** Map a single backend feed item to a typed FeedEntry. Pure (now is injectable). */
export const mapBackendItem = (
  item: BackendFeedItem,
  now: number = Date.now(),
): FeedEntry => ({
  id: item.run_id,
  agent: item.agent_key,
  action: item.action,
  time: relativeTime(item.timestamp, now),
  fullTime: formatFullTime(item.timestamp),
  status: outcomeToStatus(item.outcome),
  summary: item.summary,
  facts: item.facts ?? [],
  tokens: { used: item.tokens, cost: formatCost(item.cost_usd) },
});

/** Map a full backend report into typed entries plus an agent registry. */
export const mapReport = (
  report: BackendReport,
  now: number = Date.now(),
): LoadedFeed => {
  const entries = report.feed.map((item) => mapBackendItem(item, now));
  const agents: Record<string, AgentMeta> = {};
  for (const item of report.feed) {
    if (!agents[item.agent_key]) {
      agents[item.agent_key] = resolveAgent(item.agent_key, item.agent_name);
    }
  }
  return { entries, agents };
};

const fallback = (): LoadedFeed => ({ entries: demoFeed, agents: AGENTS });

/**
 * Load the fleet feed.
 *
 * Fetches `feed.json` (served from public/). On success maps the backend report
 * to typed entries and an agent registry. On ANY fetch/parse failure, falls back
 * to bundled demo data so the dashboard always renders.
 */
export const loadFeed = async (): Promise<LoadedFeed> => {
  try {
    const res = await fetch("feed.json");
    if (!res.ok) return fallback();
    const report = (await res.json()) as BackendReport;
    if (!report || !Array.isArray(report.feed)) return fallback();
    return mapReport(report);
  } catch {
    return fallback();
  }
};
