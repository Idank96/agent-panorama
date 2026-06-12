import { describe, expect, it } from "vitest";
import { answerSummary, applySuggestion, defToWire, fieldOf } from "./valueInterview";
import type { EditableDef } from "./valueConfig";

const def = (over: Partial<EditableDef> = {}): EditableDef => ({
  domain: "",
  userGoal: "",
  successCriteria: [],
  dimensions: [],
  ...over,
});

describe("fieldOf", () => {
  it("maps wire fields to editable keys", () => {
    expect(fieldOf("domain")).toBe("domain");
    expect(fieldOf("user_goal")).toBe("userGoal");
    expect(fieldOf("success_criteria")).toBe("successCriteria");
    expect(fieldOf("custom_dimensions")).toBe("dimensions");
    expect(fieldOf("nope")).toBeNull();
  });
});

describe("defToWire", () => {
  it("trims, nulls empties, and builds the dimension map", () => {
    const wire = defToWire(
      def({
        domain: " support ",
        userGoal: "",
        successCriteria: ["resolved", "  "],
        dimensions: [
          { name: "empathy", description: " warmth " },
          { name: "  ", description: "ignored" },
        ],
      }),
    );
    expect(wire).toEqual({
      domain: "support",
      user_goal: null,
      success_criteria: ["resolved"],
      custom_dimensions: { empathy: "warmth" },
    });
  });
});

describe("answerSummary", () => {
  it("renders a readable transcript line per field", () => {
    expect(answerSummary("domain", def({ domain: "support" }))).toBe("support");
    expect(answerSummary("success_criteria", def({ successCriteria: ["a", "b"] }))).toBe("a; b");
    expect(
      answerSummary(
        "custom_dimensions",
        def({ dimensions: [{ name: "empathy", description: "warmth" }, { name: "speed", description: "" }] }),
      ),
    ).toBe("empathy (warmth); speed");
  });
});

describe("applySuggestion", () => {
  it("replaces text fields and appends list/dimension items without duplicates", () => {
    expect(applySuggestion("domain", def(), "support").domain).toBe("support");

    const withCrit = applySuggestion("success_criteria", def(), "resolved");
    expect(withCrit.successCriteria).toEqual(["resolved"]);
    expect(applySuggestion("success_criteria", withCrit, "resolved").successCriteria).toEqual([
      "resolved",
    ]);

    const withDim = applySuggestion("custom_dimensions", def(), "empathy");
    expect(withDim.dimensions).toEqual([{ name: "empathy", description: "" }]);
    expect(applySuggestion("custom_dimensions", withDim, "empathy").dimensions).toHaveLength(1);
  });
});
