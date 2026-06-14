import type { ValueConfigResponse, ValueConfigShape, ValueDefinition } from "../types";

const VALUE_CONFIG_URL = "/api/value-config";

/** The form-friendly shape of one agent's value definition (strings, arrays). */
export interface EditableDef {
  domain: string;
  servedUser: string;
  userGoal: string;
  successCriteria: string[];
  dimensions: { name: string; description: string }[];
  failureModes: string[];
  stakesGood: string;
  stakesBad: string;
}

/** The form-friendly shape of the whole value configuration. */
export interface EditableConfig {
  judgeModel: string;
  includeSingleRuns: boolean;
  default: EditableDef;
  contexts: Record<string, EditableDef>;
}

export const blankEditableDef = (): EditableDef => ({
  domain: "",
  servedUser: "",
  userGoal: "",
  successCriteria: [],
  dimensions: [],
  failureModes: [],
  stakesGood: "",
  stakesBad: "",
});

/** Map a server value definition into the editable form shape. */
export const toEditableDef = (def: ValueDefinition | null | undefined): EditableDef => ({
  domain: def?.domain ?? "",
  servedUser: def?.served_user ?? "",
  userGoal: def?.user_goal ?? "",
  successCriteria: [...(def?.success_criteria ?? [])],
  dimensions: Object.entries(def?.custom_dimensions ?? {}).map(([name, description]) => ({
    name,
    description,
  })),
  failureModes: [...(def?.failure_modes ?? [])],
  stakesGood: def?.stakes_good ?? "",
  stakesBad: def?.stakes_bad ?? "",
});

/** A URL/key-safe slug for a manually-named agent ontology. */
export const slugify = (name: string): string =>
  name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "agent";

/**
 * A deterministic one-sentence summary of how an agent creates value, composed
 * from the definition for the Value Blueprint's executive summary (no LLM).
 */
export const fallbackSummary = (e: EditableDef): string => {
  const goal = e.userGoal.trim();
  const who = e.servedUser.trim();
  const dims = e.dimensions.map((d) => d.name.trim()).filter(Boolean);
  const audience = who ? lowerFirst(who) : "users";
  const lead = goal
    ? `This agent helps ${audience} ${lowerFirst(goal)}`
    : `This agent supports ${audience}`;
  const domainClause = e.domain.trim() ? ` in ${e.domain.trim()}` : "";
  const dimClause =
    dims.length > 0 ? `, with success measured on ${joinHuman(dims)}` : "";
  return `${stripPeriod(lead)}${domainClause}${dimClause}.`;
};

const lowerFirst = (text: string): string => (text ? text[0].toLowerCase() + text.slice(1) : text);
const stripPeriod = (text: string): string => text.replace(/[.\s]+$/, "");
const joinHuman = (items: string[]): string =>
  items.length <= 1
    ? (items[0] ?? "")
    : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

/** Whether an editable definition carries any signal worth sending. */
export const isDefinedEditable = (e: EditableDef): boolean =>
  !!(
    e.domain.trim() ||
    e.servedUser.trim() ||
    e.userGoal.trim() ||
    e.successCriteria.some((c) => c.trim()) ||
    e.dimensions.some((d) => d.name.trim()) ||
    e.failureModes.some((m) => m.trim()) ||
    e.stakesGood.trim() ||
    e.stakesBad.trim()
  );

/** Map an editable definition back to the server shape, or null when empty. */
export const fromEditableDef = (e: EditableDef): ValueDefinition | null => {
  if (!isDefinedEditable(e)) return null;
  const dimensions: Record<string, string> = {};
  for (const { name, description } of e.dimensions) {
    if (name.trim()) dimensions[name.trim()] = description.trim();
  }
  return {
    domain: e.domain.trim() || null,
    user_goal: e.userGoal.trim() || null,
    success_criteria: e.successCriteria.map((c) => c.trim()).filter(Boolean),
    custom_dimensions: dimensions,
    served_user: e.servedUser.trim() || null,
    failure_modes: e.failureModes.map((m) => m.trim()).filter(Boolean),
    stakes_good: e.stakesGood.trim() || null,
    stakes_bad: e.stakesBad.trim() || null,
  };
};

export const toEditableConfig = (raw: Partial<ValueConfigShape>): EditableConfig => ({
  judgeModel: raw.judge_model ?? "",
  includeSingleRuns: raw.include_single_runs ?? true,
  default: toEditableDef(raw.default ?? null),
  contexts: Object.fromEntries(
    Object.entries(raw.contexts ?? {}).map(([key, def]) => [key, toEditableDef(def)]),
  ),
});

export const fromEditableConfig = (e: EditableConfig): ValueConfigShape => {
  const contexts: Record<string, ValueDefinition> = {};
  for (const [key, def] of Object.entries(e.contexts)) {
    const built = fromEditableDef(def);
    if (built) contexts[key] = built;
  }
  const config: ValueConfigShape = {
    include_single_runs: e.includeSingleRuns,
    default: fromEditableDef(e.default),
    contexts,
  };
  if (e.judgeModel.trim()) config.judge_model = e.judgeModel.trim();
  return config;
};

/**
 * Load the current value configuration from the live server.
 *
 * Returns null when no live server is reachable (e.g. the static export),
 * which the Settings view renders as a read-only state.
 */
export const loadValueConfig = async (): Promise<ValueConfigResponse | null> => {
  try {
    const res = await fetch(VALUE_CONFIG_URL);
    if (!res.ok) return null;
    return (await res.json()) as ValueConfigResponse;
  } catch {
    return null;
  }
};

/** Persist the value configuration; the server re-maps and re-judges in the background. */
export const saveValueConfig = async (config: ValueConfigShape): Promise<boolean> => {
  try {
    const res = await fetch(VALUE_CONFIG_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    return res.ok;
  } catch {
    return false;
  }
};
