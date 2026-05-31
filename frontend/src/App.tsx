import { useEffect, useMemo, useState } from "react";
import type { Decision, Tweaks } from "./types";
import { AGENTS } from "./data/agents";
import { demoFeed } from "./data/demoFeed";
import { loadFeed, type LoadedFeed } from "./lib/loadFeed";
import { Sidebar, type NavId } from "./components/Sidebar";
import { Feed } from "./components/Feed";
import { DetailPanel } from "./components/DetailPanel";
import {
  TweakRadio,
  TweakSection,
  TweakSelect,
  TweaksPanel,
} from "./components/TweaksPanel";

const TWEAK_DEFAULTS: Tweaks = {
  accent: "calm",
  density: "comfortable",
  cardStyle: "border",
  font: "system",
};

const FONT_STACKS: Record<Tweaks["font"], string> = {
  system:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Helvetica Neue", Arial, sans-serif',
  helvetica: '"Helvetica Neue", Helvetica, Arial, sans-serif',
  inter: '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
};

const NAV_LABELS: Record<Exclude<NavId, "activity">, string> = {
  agents: "Agents",
  reports: "Reports",
  settings: "Settings",
};

const firstPendingId = (data: LoadedFeed): string | null => {
  const pending = data.entries.find((e) => e.status === "pending");
  if (pending) return pending.id;
  return data.entries[0]?.id ?? null;
};

export default function App() {
  const [t, setT] = useState<Tweaks>(TWEAK_DEFAULTS);
  const setTweak = <K extends keyof Tweaks>(key: K, value: Tweaks[K]) =>
    setT((prev) => ({ ...prev, [key]: value }));

  const [nav, setNav] = useState<NavId>("activity");
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});

  const [data, setData] = useState<LoadedFeed>({
    entries: demoFeed,
    agents: AGENTS,
  });
  const [selectedId, setSelectedId] = useState<string | null>(() =>
    firstPendingId({ entries: demoFeed, agents: AGENTS }),
  );

  // Pull real fleet data on mount; fall back to demo data on any failure.
  useEffect(() => {
    let active = true;
    loadFeed().then((loaded) => {
      if (!active) return;
      setData(loaded);
      setSelectedId(firstPendingId(loaded));
      setDecisions({});
      setSelectedAgent(null);
    });
    return () => {
      active = false;
    };
  }, []);

  const accentKey = t.accent === "vivid" ? "vivid" : "calm";

  // Apply font globally.
  useEffect(() => {
    document.documentElement.style.setProperty(
      "--ap-font",
      FONT_STACKS[t.font] || FONT_STACKS.system,
    );
  }, [t.font]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return data.entries.filter((e) => {
      if (selectedAgent && e.agent !== selectedAgent) return false;
      if (
        q &&
        !(
          e.action.toLowerCase().includes(q) ||
          (data.agents[e.agent]?.name ?? e.agent).toLowerCase().includes(q)
        )
      )
        return false;
      return true;
    });
  }, [query, selectedAgent, data]);

  const onDecision = (id: string, decision: Decision | null) => {
    setDecisions((prev) => {
      const next = { ...prev };
      if (decision === null) delete next[id];
      else next[id] = decision;
      return next;
    });
    if (decision) setSelectedId(id);
  };

  const selectedEntry =
    data.entries.find((e) => e.id === selectedId) ?? null;
  const filterName = selectedAgent
    ? (data.agents[selectedAgent]?.name ?? selectedAgent)
    : null;

  return (
    <div className="ap-app" data-density={t.density}>
      <Sidebar
        nav={nav}
        setNav={setNav}
        agents={data.agents}
        accentKey={accentKey}
        selectedAgent={selectedAgent}
        setSelectedAgent={setSelectedAgent}
      />

      {nav === "activity" ? (
        <Feed
          entries={filtered}
          agents={data.agents}
          accentKey={accentKey}
          cardStyle={t.cardStyle}
          selectedId={selectedId}
          onSelect={setSelectedId}
          decisions={decisions}
          onDecision={onDecision}
          query={query}
          setQuery={setQuery}
          filterName={filterName}
        />
      ) : (
        <main className="ap-feed">
          <header className="ap-topbar">
            <div className="ap-topbar-row">
              <div className="ap-topbar-title">
                <h1>{NAV_LABELS[nav]}</h1>
                <span className="ap-topbar-sub">Agent Panorama</span>
              </div>
            </div>
          </header>
          <div className="ap-placeholder">
            <div className="ap-placeholder-inner">
              <h2>{NAV_LABELS[nav]}</h2>
              <p>
                This view is out of scope for the current mockup. The Activity
                Feed holds the live design.
              </p>
            </div>
          </div>
        </main>
      )}

      <DetailPanel
        entry={nav === "activity" ? selectedEntry : null}
        agent={selectedEntry ? (data.agents[selectedEntry.agent] ?? null) : null}
        accentKey={accentKey}
        decision={selectedEntry ? decisions[selectedEntry.id] : undefined}
        onDecision={onDecision}
      />

      <TweaksPanel title="Tweaks">
        <TweakSection label="Appearance" />
        <TweakRadio
          label="Accent intensity"
          value={t.accent}
          options={[
            { value: "calm", label: "Calm" },
            { value: "vivid", label: "Vivid" },
          ]}
          onChange={(v) => setTweak("accent", v as Tweaks["accent"])}
        />
        <TweakRadio
          label="Feed density"
          value={t.density}
          options={[
            { value: "compact", label: "Compact" },
            { value: "comfortable", label: "Comfortable" },
          ]}
          onChange={(v) => setTweak("density", v as Tweaks["density"])}
        />
        <TweakSection label="Card treatment" />
        <TweakRadio
          label="Style"
          value={t.cardStyle}
          options={[
            { value: "border", label: "Border" },
            { value: "rail", label: "Rail" },
            { value: "minimal", label: "Plain" },
          ]}
          onChange={(v) => setTweak("cardStyle", v as Tweaks["cardStyle"])}
        />
        <TweakSection label="Typography" />
        <TweakSelect
          label="Font"
          value={t.font}
          options={[
            { value: "system", label: "System UI" },
            { value: "helvetica", label: "Helvetica Neue" },
            { value: "inter", label: "IBM Plex Sans" },
          ]}
          onChange={(v) => setTweak("font", v as Tweaks["font"])}
        />
      </TweaksPanel>
    </div>
  );
}
