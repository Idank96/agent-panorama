import { useEffect, useMemo, useState } from "react";
import type { Decision } from "./types";
import { AGENTS } from "./data/agents";
import { demoFeed } from "./data/demoFeed";
import { loadFeed, type LoadedFeed } from "./lib/loadFeed";
import { Sidebar, type NavId } from "./components/Sidebar";
import { Feed } from "./components/Feed";
import { DetailPanel } from "./components/DetailPanel";

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
    <div className="ap-app">
      <Sidebar
        nav={nav}
        setNav={setNav}
        agents={data.agents}
        selectedAgent={selectedAgent}
        setSelectedAgent={setSelectedAgent}
      />

      {nav === "activity" ? (
        <Feed
          entries={filtered}
          agents={data.agents}
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
        decision={selectedEntry ? decisions[selectedEntry.id] : undefined}
        onDecision={onDecision}
      />
    </div>
  );
}
