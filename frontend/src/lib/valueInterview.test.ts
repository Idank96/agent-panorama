import { describe, expect, it } from "vitest";
import { answerSummary, applySuggestion, defToWire } from "./valueInterview";
import { blankEditableDef, type EditableDef } from "./valueConfig";

const def = (over: Partial<EditableDef> = {}): EditableDef => ({
  ...blankEditableDef(),
  ...over,
});

describe("defToWire", () => {
  it("trims, nulls empties, and builds the dimension map", () => {
    const wire = defToWire(
      def({
        domain: " support ",
        successCriteria: ["resolved", "  "],
        dimensions: [
          { name: "empathy", description: " warmth " },
          { name: "  ", description: "ignored" },
        ],
        failureModes: ["wrong amount", "  "],
        stakesGood: " saves time ",
      }),
    );
    expect(wire).toEqual({
      domain: "support",
      user_goal: null,
      success_criteria: ["resolved"],
      custom_dimensions: { empathy: "warmth" },
      served_user: null,
      failure_modes: ["wrong amount"],
      stakes_good: "saves time",
      stakes_bad: null,
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

  it("handles the new ontology fields", () => {
    expect(applySuggestion("served_user", def(), "a customer").servedUser).toBe("a customer");
    expect(applySuggestion("stakes_bad", def(), "a chargeback").stakesBad).toBe("a chargeback");
    const withMode = applySuggestion("failure_modes", def(), "wrong amount");
    expect(withMode.failureModes).toEqual(["wrong amount"]);
    expect(answerSummary("failure_modes", withMode)).toBe("wrong amount");
  });
});
