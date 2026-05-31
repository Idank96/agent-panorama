import type { AgentMeta, Status } from "../types";

// Agent registry. Accent colors are calm/desaturated.
export const AGENTS: Record<string, AgentMeta> = {
  scheduling: {
    id: "scheduling",
    name: "Scheduling Agent",
    short: "SC",
    health: "green",
    accent: "#4b6b9a",
    tint: "#eef2f8",
  },
  hr: {
    id: "hr",
    name: "HR Agent",
    short: "HR",
    health: "green",
    accent: "#4f8a6e",
    tint: "#eef5f1",
  },
  funding: {
    id: "funding",
    name: "Funding Agent",
    short: "FN",
    health: "amber",
    accent: "#9c7d3e",
    tint: "#f6f1e7",
  },
  ops: {
    id: "ops",
    name: "Ops Agent",
    short: "OP",
    health: "red",
    accent: "#a35d52",
    tint: "#f7eeec",
  },
};

export const STATUS: Record<Status, { label: string; kind: Status }> = {
  completed: { label: "Completed", kind: "completed" },
  pending: { label: "Pending Approval", kind: "pending" },
  failed: { label: "Failed", kind: "failed" },
};

// Deterministic calm color pairs for agent keys not in the registry
// (e.g. the backend's "research-assistant"). Picked by hashing the key so a
// given agent always gets the same color across renders.
const PALETTE: { accent: string; tint: string }[] = [
  { accent: "#4b6b9a", tint: "#eef2f8" },
  { accent: "#4f8a6e", tint: "#eef5f1" },
  { accent: "#9c7d3e", tint: "#f6f1e7" },
  { accent: "#a35d52", tint: "#f7eeec" },
  { accent: "#6a5b9a", tint: "#f1eff7" },
  { accent: "#3f8f93", tint: "#eaf4f4" },
];

const hashKey = (key: string): number => {
  let h = 0;
  for (let i = 0; i < key.length; i += 1) {
    h = (h * 31 + key.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
};

const initials = (name: string): string => {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "AG";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
};

const healthFromKey = (key: string): AgentMeta["health"] => {
  const healths: AgentMeta["health"][] = ["green", "amber", "red"];
  return healths[hashKey(key) % healths.length];
};

/**
 * Resolve agent metadata for a feed entry's agent key.
 *
 * Returns the registered AgentMeta when the key exists in AGENTS; otherwise
 * builds a stable entry using a hashed palette fallback so unknown agent keys
 * still render with consistent colors.
 */
export const resolveAgent = (key: string, name: string): AgentMeta => {
  const known = AGENTS[key];
  if (known) return known;
  const palette = PALETTE[hashKey(key) % PALETTE.length];
  return {
    id: key,
    name: name || key,
    short: initials(name || key),
    health: healthFromKey(key),
    accent: palette.accent,
    tint: palette.tint,
  };
};
