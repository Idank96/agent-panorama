import { afterEach, describe, expect, it, vi } from "vitest";
import {
  blankEditableDef,
  fromEditableConfig,
  fromEditableDef,
  isDefinedEditable,
  loadValueConfig,
  toEditableConfig,
  toEditableDef,
} from "./valueConfig";
import type { ValueConfigResponse, ValueConfigShape, ValueDefinition } from "../types";

const sampleDef = (): ValueDefinition => ({
  domain: "customer support",
  user_goal: "resolve the billing issue",
  success_criteria: ["refund processed", "no repeat contact"],
  custom_dimensions: { empathy: "warmth and acknowledgement" },
  served_user: "a frustrated customer",
  failure_modes: ["wrong refund amount"],
  stakes_good: "saves agent time",
  stakes_bad: "triggers a chargeback",
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
      ...blankEditableDef(),
      domain: " support ",
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
      served_user: null,
      failure_modes: [],
      stakes_good: null,
      stakes_bad: null,
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

const configResponse = (): ValueConfigResponse => ({
  enabled: true,
  config: { default: sampleDef(), contexts: {} },
  agents: [{ key: "support-agent", name: "support-agent" }],
  mappings: {},
  ontology: { archetypes: {}, primitives: {} },
  blueprint: [],
});

const okResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;
const notFound = () => ({ ok: false, json: async () => ({}) }) as Response;

describe("loadValueConfig source fallback", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("returns the live config as editable when the server answers", async () => {
    const body = configResponse();
    const fetchMock = vi.fn(async () => okResponse(body));
    vi.stubGlobal("fetch", fetchMock);
    const loaded = await loadValueConfig();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/value-config");
    expect(loaded).toEqual({ response: body, live: true });
  });

  it("falls back to the static export as read-only when no server", async () => {
    const body = configResponse();
    const fetchMock = vi.fn(async (url: string) =>
      url === "/api/value-config" ? notFound() : okResponse(body),
    );
    vi.stubGlobal("fetch", fetchMock);
    const loaded = await loadValueConfig();
    expect(fetchMock).toHaveBeenNthCalledWith(2, "value-config.json");
    expect(loaded).toEqual({ response: body, live: false });
  });

  it("returns null when neither source is reachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => notFound()));
    expect(await loadValueConfig()).toBeNull();
  });
});
