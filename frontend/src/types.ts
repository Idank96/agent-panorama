export type Status = "completed" | "pending" | "failed";

export type Outcome = "success" | "human-escalated" | "failure" | "unknown";

export type Decision = "approved" | "rejected";

export interface AgentMeta {
  id: string;
  name: string;
  short: string;
  health: "green" | "amber" | "red";
  accent: string;
  tint: string;
}

/** The value layer's verdict on one conversation (scores are 0-10). */
export interface ValueJudgment {
  overall_score: number;
  goal_completion: number;
  response_quality: number;
  efficiency: number;
  outcome: string;
  rationale: string;
  value_delivered: string[];
  value_lost: string[];
  recommended_fixes: string[];
  custom_scores: Record<string, number>;
  criteria_verdicts: Record<string, boolean>;
}

/** Per-agent value metrics, mapped from a backend rollup. */
export interface ValueRollup {
  agentKey: string;
  agentName: string;
  runs: number;
  sessions: number;
  judged: number;
  avgValueScore: number | null;
  valuableRate: number | null;
  costPerValuable: string | null;
  totalCost: string | null;
}

/** Fleet-level value summary (totals.value in the JSON contract). */
export interface ValueTotals {
  judged: number;
  avgValueScore: number | null;
  valuableRate: number | null;
  costPerValuable: string | null;
}

/** One agent's customer-defined value definition (the editable "object"). */
export interface ValueDefinition {
  domain: string | null;
  user_goal: string | null;
  success_criteria: string[];
  custom_dimensions: Record<string, string>;
}

/** The whole value configuration, as sent to / received from the server. */
export interface ValueConfigShape {
  judge_model?: string;
  max_judgments?: number;
  include_single_runs?: boolean;
  default: ValueDefinition | null;
  contexts: Record<string, ValueDefinition>;
}

/** Read-only canonical mapping for one agent ("how we mapped you"). */
export interface AgentMappingView {
  agent_key: string;
  archetype: string;
  archetype_description: string;
  archetype_confidence: number;
  dimension_to_primitive: Record<string, string>;
  criterion_to_primitive: Record<string, string>;
  source: string;
}

/** The GET /api/value-config payload. */
export interface ValueConfigResponse {
  enabled: boolean;
  config: Partial<ValueConfigShape>;
  agents: { key: string; name: string }[];
  mappings: Record<string, AgentMappingView>;
  ontology: {
    archetypes: Record<string, string>;
    primitives: Record<string, string>;
  };
}

export interface FeedEntry {
  id: string;
  agent: string;
  action: string;
  time: string;
  fullTime: string;
  status: Status;
  summary: string;
  facts: [string, string][];
  tokens: { used: number; cost: string | null };
  policy?: { rule: string; detail: string };
  value?: ValueJudgment | null;
}
