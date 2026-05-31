import type { AgentMeta, Status } from "../types";

// Agent registry. Accent colors are calm/desaturated by default; a "vivid"
// variant is supplied for the Tweaks accent-intensity option.
export const AGENTS: Record<string, AgentMeta> = {
  scheduling: {
    id: "scheduling",
    name: "Scheduling Agent",
    short: "SC",
    health: "green",
    accent: { calm: "#4b6b9a", vivid: "#2f5fbf" },
    tint: { calm: "#eef2f8", vivid: "#e7eefc" },
  },
  hr: {
    id: "hr",
    name: "HR Agent",
    short: "HR",
    health: "green",
    accent: { calm: "#4f8a6e", vivid: "#1f9a63" },
    tint: { calm: "#eef5f1", vivid: "#e6f5ed" },
  },
  funding: {
    id: "funding",
    name: "Funding Agent",
    short: "FN",
    health: "amber",
    accent: { calm: "#9c7d3e", vivid: "#c08a1e" },
    tint: { calm: "#f6f1e7", vivid: "#fbf2dd" },
  },
  ops: {
    id: "ops",
    name: "Ops Agent",
    short: "OP",
    health: "red",
    accent: { calm: "#a35d52", vivid: "#c64b3c" },
    tint: { calm: "#f7eeec", vivid: "#fceae6" },
  },
};

export const STATUS: Record<Status, { label: string; kind: Status }> = {
  completed: { label: "Completed", kind: "completed" },
  pending: { label: "Pending Approval", kind: "pending" },
  failed: { label: "Failed", kind: "failed" },
};

// Deterministic calm/vivid color pairs for agent keys not in the registry
// (e.g. the backend's "research-assistant"). Picked by hashing the key so a
// given agent always gets the same color across renders.
const PALETTE: { accent: AgentMeta["accent"]; tint: AgentMeta["tint"] }[] = [
  { accent: { calm: "#4b6b9a", vivid: "#2f5fbf" }, tint: { calm: "#eef2f8", vivid: "#e7eefc" } },
  { accent: { calm: "#4f8a6e", vivid: "#1f9a63" }, tint: { calm: "#eef5f1", vivid: "#e6f5ed" } },
  { accent: { calm: "#9c7d3e", vivid: "#c08a1e" }, tint: { calm: "#f6f1e7", vivid: "#fbf2dd" } },
  { accent: { calm: "#a35d52", vivid: "#c64b3c" }, tint: { calm: "#f7eeec", vivid: "#fceae6" } },
  { accent: { calm: "#6a5b9a", vivid: "#7a52cf" }, tint: { calm: "#f1eff7", vivid: "#efe6fc" } },
  { accent: { calm: "#3f8f93", vivid: "#1f9aa0" }, tint: { calm: "#eaf4f4", vivid: "#e0f5f6" } },
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
