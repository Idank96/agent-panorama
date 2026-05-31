export type Status = "completed" | "pending" | "failed";

export type Outcome = "success" | "human-escalated" | "failure" | "unknown";

export type Decision = "approved" | "rejected";

export interface AgentMeta {
  id: string;
  name: string;
  short: string;
  health: "green" | "amber" | "red";
  accent: { calm: string; vivid: string };
  tint: { calm: string; vivid: string };
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
}

export interface Tweaks {
  accent: "calm" | "vivid";
  density: "compact" | "comfortable";
  cardStyle: "border" | "rail" | "minimal";
  font: "system" | "helvetica" | "inter";
}
