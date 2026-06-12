import { describe, expect, it } from "vitest";
import {
  fromEditableConfig,
  fromEditableDef,
  isDefinedEditable,
  toEditableConfig,
  toEditableDef,
} from "./valueConfig";
import type { ValueConfigShape, ValueDefinition } from "../types";

const sampleDef = (): ValueDefinition => ({
  domain: "customer support",
  user_goal: "resolve the billing issue",
  success_criteria: ["refund processed", "no repeat contact"],
  custom_dimensions: { empathy: "warmth and acknowledgement" },
});

describe("value definition round-trip", () => {
  it("survives toEditableDef -> fromEditableDef", () => {
    expect(fromEditableDef(toEditableDef(sampleDef()))).toEqual(sampleDef());
  });

  it("treats an empty definition as null", () => {
    expect(fromEditableDef(toEditableDef(null))).toBeNull();
    expect(isDefinedEditable(toEditableDef(null))).toBe(false);
  });

  it("drops blank criteria and unnamed dimensions on the way out", () => {
    const built = fromEditableDef({
      domain: " support ",
      userGoal: "",
      successCriteria: ["kept", "  ", ""],
      dimensions: [
        { name: "empathy", description: "warmth" },
        { name: "  ", description: "ignored" },
      ],
    });
    expect(built).toEqual({
      domain: "support",
      user_goal: null,
      success_criteria: ["kept"],
      custom_dimensions: { empathy: "warmth" },
    });
  });
});

describe("value config round-trip", () => {
  it("survives toEditableConfig -> fromEditableConfig", () => {
    const raw: Partial<ValueConfigShape> = {
      judge_model: "google_genai:gemini-2.5-flash",
      include_single_runs: false,
      default: sampleDef(),
      contexts: { "support-bot": sampleDef() },
    };
    const restored = fromEditableConfig(toEditableConfig(raw));
    expect(restored.default).toEqual(sampleDef());
    expect(restored.contexts["support-bot"]).toEqual(sampleDef());
    expect(restored.include_single_runs).toBe(false);
    expect(restored.judge_model).toBe("google_genai:gemini-2.5-flash");
  });

  it("omits agents whose definition was cleared", () => {
    const editable = toEditableConfig({ contexts: { "ghost": null as never } });
    const restored = fromEditableConfig(editable);
    expect(restored.contexts).toEqual({});
    expect(restored.default).toBeNull();
  });
});
