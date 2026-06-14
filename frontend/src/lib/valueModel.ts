import type { BlueprintObject } from "../types";
import type { EditableDef } from "./valueConfig";

export type ObjectState = "missing" | "thin" | "suggested" | "complete";

export interface ObjectStatusView {
  state: ObjectState;
  summary: string;
  filled: number;
}

/** How many entries a blueprint field currently holds in the editable def. */
export const filledCount = (def: EditableDef, fieldKey: string): number => {
  switch (fieldKey) {
    case "domain":
      return def.domain.trim() ? 1 : 0;
    case "served_user":
      return def.servedUser.trim() ? 1 : 0;
    case "user_goal":
      return def.userGoal.trim() ? 1 : 0;
    case "success_criteria":
      return def.successCriteria.filter((c) => c.trim()).length;
    case "custom_dimensions":
      return def.dimensions.filter((d) => d.name.trim()).length;
    case "failure_modes":
      return def.failureModes.filter((m) => m.trim()).length;
    case "stakes_good":
      return def.stakesGood.trim() ? 1 : 0;
    case "stakes_bad":
      return def.stakesBad.trim() ? 1 : 0;
    default:
      return 0;
  }
};

const LIST_KINDS = new Set(["list", "dimensions"]);

const propertySatisfied = (obj: BlueprintObject, fieldKey: string, kind: string, def: EditableDef) =>
  LIST_KINDS.has(kind)
    ? filledCount(def, fieldKey) >= Math.max(obj.min_count, 1)
    : filledCount(def, fieldKey) >= 1;

const objectSummary = (obj: BlueprintObject, def: EditableDef): string => {
  const pieces: string[] = [];
  for (const prop of obj.properties) {
    const count = filledCount(def, prop.key);
    if (!count) continue;
    if (LIST_KINDS.has(prop.kind)) {
      pieces.push(`${count} ${prop.label.toLowerCase()}`);
    } else {
      const text = fieldText(def, prop.key);
      pieces.push(text.length <= 40 ? text : text.slice(0, 39) + "…");
    }
  }
  return pieces.join(" · ");
};

const fieldText = (def: EditableDef, fieldKey: string): string => {
  switch (fieldKey) {
    case "domain":
      return def.domain.trim();
    case "served_user":
      return def.servedUser.trim();
    case "user_goal":
      return def.userGoal.trim();
    case "stakes_good":
      return def.stakesGood.trim();
    case "stakes_bad":
      return def.stakesBad.trim();
    default:
      return "";
  }
};

/** The fill state of one blueprint object for the current editable def. */
export const objectStatusOf = (obj: BlueprintObject, def: EditableDef): ObjectStatusView => {
  const filled = obj.properties.reduce((sum, p) => sum + filledCount(def, p.key), 0);
  const satisfied = obj.properties.every((p) => propertySatisfied(obj, p.key, p.kind, def));
  let state: ObjectState;
  if (satisfied && filled > 0) {
    state = "complete";
  } else if (obj.importance === "required") {
    state = filled > 0 ? "thin" : "missing";
  } else {
    state = filled > 0 ? "complete" : "suggested";
  }
  return { state, summary: objectSummary(obj, def), filled };
};

/** Status for every blueprint object, keyed by object key. */
export const objectStatus = (
  blueprint: BlueprintObject[],
  def: EditableDef,
): Record<string, ObjectStatusView> =>
  Object.fromEntries(blueprint.map((obj) => [obj.key, objectStatusOf(obj, def)]));

const STATE_WEIGHT: Record<ObjectState, number> = {
  complete: 1,
  thin: 0.5,
  missing: 0,
  suggested: 0,
};

/**
 * How complete a value definition is, as a 0-100 percentage.
 *
 * Each blueprint object contributes its fill weight (complete = full, thin =
 * half, missing/suggested = none) so the score reflects how much of the whole
 * picture the manager has actually defined.
 */
export const blueprintCompleteness = (blueprint: BlueprintObject[], def: EditableDef): number => {
  if (blueprint.length === 0) return 0;
  const status = objectStatus(blueprint, def);
  const score = blueprint.reduce((sum, obj) => sum + STATE_WEIGHT[status[obj.key].state], 0);
  return Math.round((score / blueprint.length) * 100);
};
