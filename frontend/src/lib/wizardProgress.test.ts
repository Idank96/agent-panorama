import { describe, expect, it } from "vitest";
import { wizardProgress } from "./wizardProgress";
import { blankEditableDef, type EditableDef } from "./valueConfig";
import type { BlueprintObject } from "../types";

const obj = (key: string, over: Partial<BlueprintObject> = {}): BlueprintObject => ({
  key,
  label: key,
  description: "",
  importance: "required",
  layout: { col: 0, row: 0 },
  links: [],
  properties: [{ key: "domain", label: "Domain", kind: "text", help: "", examples: [] }],
  min_count: 0,
  ...over,
});

const def = (over: Partial<EditableDef> = {}): EditableDef => ({ ...blankEditableDef(), ...over });

// A small blueprint whose single property maps to a different def field per object.
const goal = obj("goal", {
  properties: [{ key: "user_goal", label: "Goal", kind: "longtext", help: "", examples: [] }],
});
const stakes = obj("stakes", {
  importance: "recommended",
  properties: [{ key: "stakes_good", label: "Worth", kind: "longtext", help: "", examples: [] }],
});
const blueprint = [obj("agent"), goal, stakes];

describe("wizardProgress", () => {
  it("treats every object as to-do when nothing is filled", () => {
    const p = wizardProgress(blueprint, def(), null);
    expect(p.completed).toEqual([]);
    expect(p.active).toBeNull();
    expect(p.todo).toEqual(["agent", "goal", "stakes"]);
    expect(p.stepIndex).toBe(0);
    expect(p.fraction).toBe(0);
  });

  it("counts filled objects as completed and excludes the active one", () => {
    const p = wizardProgress(blueprint, def({ domain: "support" }), "goal");
    expect(p.completed).toEqual(["agent"]);
    expect(p.active).toBe("goal");
    expect(p.todo).toEqual(["stakes"]);
    expect(p.stepIndex).toBe(2);
    expect(p.total).toBe(3);
    expect(p.fraction).toBeCloseTo(2 / 3);
  });

  it("ignores an active key that is not in the blueprint", () => {
    const p = wizardProgress(blueprint, def({ domain: "support" }), "ghost");
    expect(p.active).toBeNull();
    expect(p.completed).toEqual(["agent"]);
    expect(p.stepIndex).toBe(1);
  });
});
