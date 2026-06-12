import type { ValueConfigResponse, ValueConfigShape, ValueDefinition } from "../types";

const VALUE_CONFIG_URL = "/api/value-config";

/** The form-friendly shape of one agent's value definition (strings, arrays). */
export interface EditableDef {
  domain: string;
  userGoal: string;
  successCriteria: string[];
  dimensions: { name: string; description: string }[];
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
  userGoal: "",
  successCriteria: [],
  dimensions: [],
});

/** Map a server value definition into the editable form shape. */
export const toEditableDef = (def: ValueDefinition | null | undefined): EditableDef => ({
  domain: def?.domain ?? "",
  userGoal: def?.user_goal ?? "",
  successCriteria: [...(def?.success_criteria ?? [])],
  dimensions: Object.entries(def?.custom_dimensions ?? {}).map(([name, description]) => ({
    name,
    description,
  })),
});

/** Whether an editable definition carries any signal worth sending. */
export const isDefinedEditable = (e: EditableDef): boolean =>
  !!(
    e.domain.trim() ||
    e.userGoal.trim() ||
    e.successCriteria.some((c) => c.trim()) ||
    e.dimensions.some((d) => d.name.trim())
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
