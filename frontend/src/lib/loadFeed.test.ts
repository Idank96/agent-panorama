import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadFeed,
  mapBackendItem,
  mapReport,
  outcomeToStatus,
  type BackendFeedItem,
  type BackendReport,
} from "./loadFeed";
import { demoFeed } from "../data/demoFeed";
import type { Outcome } from "../types";

const NOW = Date.parse("2026-05-31T10:00:00Z");

const baseItem = (over: Partial<BackendFeedItem> = {}): BackendFeedItem => ({
  run_id: "run-1",
  agent_name: "Research Assistant",
  agent_key: "research-assistant",
  action: "Summarized 12 papers",
  outcome: "success",
  timestamp: "2026-05-31T09:58:00Z",
  retry_count: 0,
  anomaly_count: 0,
  tokens: 4200,
  cost_usd: 0.0123,
  summary: "Did the thing.",
  facts: [["Papers", "12"]],
  anomalies: [],
  ...over,
});

describe("outcomeToStatus", () => {
  const cases: [Outcome, string][] = [
    ["success", "completed"],
    ["human-escalated", "pending"],
    ["failure", "failed"],
    ["unknown", "completed"],
  ];
  it.each(cases)("maps %s -> %s", (outcome, status) => {
    expect(outcomeToStatus(outcome)).toBe(status);
  });
});

describe("mapBackendItem", () => {
  it("maps outcome to status for all four outcomes", () => {
    expect(mapBackendItem(baseItem({ outcome: "success" }), NOW).status).toBe(
      "completed",
    );
    expect(
      mapBackendItem(baseItem({ outcome: "human-escalated" }), NOW).status,
    ).toBe("pending");
    expect(mapBackendItem(baseItem({ outcome: "failure" }), NOW).status).toBe(
      "failed",
    );
    expect(mapBackendItem(baseItem({ outcome: "unknown" }), NOW).status).toBe(
      "completed",
    );
  });

  it("formats cost when present", () => {
    const entry = mapBackendItem(baseItem({ cost_usd: 0.0123 }), NOW);
    expect(entry.tokens.cost).toBe("$0.0123");
    expect(entry.tokens.used).toBe(4200);
  });

  it("leaves cost null when absent", () => {
    const entry = mapBackendItem(baseItem({ cost_usd: null }), NOW);
    expect(entry.tokens.cost).toBeNull();
    expect(entry.tokens.used).toBe(4200);
  });

  it("passes facts through and omits policy", () => {
    const entry = mapBackendItem(baseItem(), NOW);
    expect(entry.facts).toEqual([["Papers", "12"]]);
    expect(entry.policy).toBeUndefined();
  });

  it("renders relative time and falls back to raw ISO when unparseable", () => {
    expect(mapBackendItem(baseItem(), NOW).time).toBe("2m ago");
    const bad = mapBackendItem(baseItem({ timestamp: "not-a-date" }), NOW);
    expect(bad.time).toBe("not-a-date");
  });
});

describe("mapReport", () => {
  it("builds entries and a deduped agent registry from the feed", () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: { runs: 2, steps: 4, tokens: 8400, cost_usd: 0.02 },
      feed: [
        baseItem({ run_id: "a", agent_key: "research-assistant" }),
        baseItem({ run_id: "b", agent_key: "research-assistant" }),
      ],
      rollups: [],
      decision_log: [],
    };
    const { entries, agents } = mapReport(report, NOW);
    expect(entries).toHaveLength(2);
    expect(Object.keys(agents)).toEqual(["research-assistant"]);
    // Unknown key still resolves to a stable AgentMeta.
    expect(agents["research-assistant"].accent).toMatch(/^#/);
  });
});

describe("loadFeed", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to demo data when fetch rejects", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("no network"))),
    );
    const result = await loadFeed();
    expect(result.entries).toBe(demoFeed);
  });

  it("falls back to demo data when response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: false, json: () => Promise.resolve({}) }),
      ),
    );
    const result = await loadFeed();
    expect(result.entries).toBe(demoFeed);
  });

  it("maps real data when fetch succeeds", async () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: { runs: 1, steps: 1, tokens: 4200, cost_usd: 0.0123 },
      feed: [baseItem()],
      rollups: [],
      decision_log: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(report) }),
      ),
    );
    const result = await loadFeed();
    expect(result.entries).toHaveLength(1);
    expect(result.entries[0].agent).toBe("research-assistant");
  });

  it("tries the live server first, then falls back to the static feed", async () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: { runs: 1, steps: 1, tokens: 4200, cost_usd: null },
      feed: [baseItem()],
      rollups: [],
      decision_log: [],
    };
    const fetchMock = vi.fn((url: string) =>
      url === "/api/report"
        ? Promise.reject(new Error("server down"))
        : Promise.resolve({ ok: true, json: () => Promise.resolve(report) }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const result = await loadFeed();
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/report");
    expect(fetchMock).toHaveBeenNthCalledWith(2, "feed.json");
    expect(result.entries).toHaveLength(1);
  });

  it("threads the injected now into relative-time mapping", async () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: { runs: 1, steps: 1, tokens: 4200, cost_usd: null },
      feed: [baseItem()],
      rollups: [],
      decision_log: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(report) }),
      ),
    );
    const result = await loadFeed(NOW);
    expect(result.entries[0].time).toBe("2m ago");
  });
});

describe("value layer mapping", () => {
  const judgment = {
    overall_score: 7,
    goal_completion: 8,
    response_quality: 7,
    efficiency: 6,
    outcome: "student got unstuck",
    rationale: "cited evidence",
    value_delivered: ["explained moon phases"],
    value_lost: [],
    recommended_fixes: [],
    custom_scores: {},
    criteria_verdicts: { "understood the concept": true },
  };

  it("passes a judgment through and defaults to null when absent", () => {
    expect(mapBackendItem(baseItem({ value: judgment })).value).toEqual(
      judgment,
    );
    expect(mapBackendItem(baseItem()).value).toBeNull();
  });

  it("maps rollup value metrics and totals.value", () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: {
        runs: 1,
        steps: 1,
        tokens: 4200,
        cost_usd: 0.0123,
        value: {
          judged: 3,
          avg_value_score: 7.5,
          valuable_rate: 0.66,
          cost_per_valuable_usd: 0.0062,
        },
      },
      feed: [baseItem({ value: judgment })],
      rollups: [
        {
          agent_name: "Research Assistant",
          agent_key: "research-assistant",
          runs: 3,
          sessions: 2,
          total_cost_usd: 0.0123,
          judged: 3,
          avg_value_score: 7.5,
          valuable_rate: 0.66,
          cost_per_valuable_usd: 0.0062,
        },
      ],
      decision_log: [],
    };
    const result = mapReport(report, NOW);
    expect(result.rollups).toHaveLength(1);
    expect(result.rollups[0].avgValueScore).toBe(7.5);
    expect(result.rollups[0].costPerValuable).toBe("$0.0062");
    expect(result.valueTotals?.judged).toBe(3);
    expect(result.valueTotals?.costPerValuable).toBe("$0.0062");
  });

  it("tolerates pre-value payloads: no value keys anywhere", () => {
    const report: BackendReport = {
      generated_at: "2026-05-31T10:00:00Z",
      time_range: { start: null, end: null },
      totals: { runs: 1, steps: 1, tokens: 4200, cost_usd: null },
      feed: [baseItem()],
      rollups: [
        { agent_name: "Research Assistant", agent_key: "research-assistant", runs: 1 },
      ],
      decision_log: [],
    };
    const result = mapReport(report, NOW);
    expect(result.valueTotals).toBeNull();
    expect(result.entries[0].value).toBeNull();
    expect(result.rollups[0].judged).toBe(0);
    expect(result.rollups[0].avgValueScore).toBeNull();
  });
});
