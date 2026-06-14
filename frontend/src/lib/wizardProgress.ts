import type { BlueprintObject } from "../types";
import type { EditableDef } from "./valueConfig";
import { objectStatus } from "./valueModel";

/** Progression of the guided wizard across the blueprint's objects. */
export interface WizardProgress {
  total: number;
  stepIndex: number;
  fraction: number;
  completed: string[];
  active: string | null;
  todo: string[];
}

/**
 * Bucket the blueprint's objects into completed / active / to-do for the wizard's
 * progress sidebar and the live map, and derive a step index and fill fraction.
 *
 * An object counts as completed once it holds any content (filled > 0) and is not
 * the one currently being asked about; the active object is the interview's current
 * step; everything else is still to do. The step index is the position of the active
 * step in that sequence (completed + the active one).
 *
 * Args:
 *   blueprint: The ontology objects, in display order.
 *   def: The value definition filled in so far.
 *   activeKey: The object key the current question targets, if any.
 *
 * Returns:
 *   A WizardProgress with ordered key buckets and a 0..1 fraction.
 */
export const wizardProgress = (
  blueprint: BlueprintObject[],
  def: EditableDef,
  activeKey: string | null,
): WizardProgress => {
  const status = objectStatus(blueprint, def);
  const completed: string[] = [];
  const todo: string[] = [];
  for (const obj of blueprint) {
    if (obj.key === activeKey) continue;
    (status[obj.key]?.filled ? completed : todo).push(obj.key);
  }
  const active = activeKey && blueprint.some((o) => o.key === activeKey) ? activeKey : null;
  const total = blueprint.length;
  const stepIndex = Math.min(completed.length + (active ? 1 : 0), total);
  return {
    total,
    stepIndex,
    fraction: total ? stepIndex / total : 0,
    completed,
    active,
    todo,
  };
};
