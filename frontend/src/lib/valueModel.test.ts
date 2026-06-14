import { describe, expect, it } from "vitest";
import { blueprintCompleteness, objectStatus, objectStatusOf } from "./valueModel";
import { blankEditableDef, type EditableDef } from "./valueConfig";
import type { BlueprintObject } from "../types";

const obj = (over: Partial<BlueprintObject>): BlueprintObject => ({
  key: "agent",
  label: "Agent",
  description: "",
  importance: "required",
  layout: { col: 0, row: 0 },
  links: [],
  properties: [{ key: "domain", label: "Domain", kind: "text", help: "", examples: [] }],
  min_count: 0,
  ...over,
});

const def = (over: Partial<EditableDef> = {}): EditableDef => ({
  ...blankEditableDef(),
  ...over,
});

describe("objectStatusOf", () => {
  it("marks a required, empty object as missing", () => {
    expect(objectStatusOf(obj({}), def()).state).toBe("missing");
  });

  it("marks a required scalar as complete once filled", () => {
    expect(objectStatusOf(obj({}), def({ domain: "support" })).state).toBe("complete");
  });

  it("marks a list below its minimum as thin", () => {
    const criteria = obj({
      key: "success_criteria",
      properties: [
        { key: "success_criteria", label: "Success criteria", kind: "list", help: "", examples: [] },
      ],
      min_count: 2,
    });
    expect(objectStatusOf(criteria, def({ successCriteria: ["only one"] })).state).toBe("thin");
    expect(objectStatusOf(criteria, def({ successCriteria: ["a", "b"] })).state).toBe("complete");
  });

  it("marks a recommended, empty object as suggested", () => {
    const stakes = obj({
      key: "stakes",
      importance: "recommended",
      properties: [
        { key: "stakes_good", label: "Worth", kind: "longtext", help: "", examples: [] },
      ],
    });
    expect(objectStatusOf(stakes, def()).state).toBe("suggested");
    expect(objectStatusOf(stakes, def({ stakesGood: "saves time" })).state).toBe("complete");
  });
});

describe("objectStatus", () => {
  it("returns a status per blueprint object", () => {
    const blueprint = [obj({ key: "agent" }), obj({ key: "goal" })];
    const status = objectStatus(blueprint, def({ domain: "support" }));
    expect(Object.keys(status)).toEqual(["agent", "goal"]);
    expect(status.agent.state).toBe("complete");
  });
});

describe("blueprintCompleteness", () => {
  const goal = obj({
    key: "goal",
    properties: [{ key: "user_goal", label: "Goal", kind: "longtext", help: "", examples: [] }],
  });

  it("is 0 for an empty definition", () => {
    expect(blueprintCompleteness([obj({}), goal], def())).toBe(0);
  });

  it("is 100 when every object is complete", () => {
    expect(blueprintCompleteness([obj({}), goal], def({ domain: "support", userGoal: "fix it" }))).toBe(
      100,
    );
  });

  it("counts a half-filled list object as partial", () => {
    const criteria = obj({
      key: "success_criteria",
      properties: [
        { key: "success_criteria", label: "Success criteria", kind: "list", help: "", examples: [] },
      ],
      min_count: 2,
    });
    // agent complete (1) + criteria thin (0.5) of 2 objects → 75%.
    expect(
      blueprintCompleteness([obj({}), criteria], def({ domain: "support", successCriteria: ["one"] })),
    ).toBe(75);
  });
});
