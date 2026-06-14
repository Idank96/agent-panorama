import type { AgentMeta } from "../types";
import {
  IconActivity,
  IconAgents,
  IconReports,
  IconSettings,
  IconValue,
} from "../icons";

export type NavId = "activity" | "value" | "agents" | "reports" | "settings";

interface SidebarProps {
  nav: NavId;
  setNav: (id: NavId) => void;
  agents: Record<string, AgentMeta>;
  selectedAgent: string | null;
  setSelectedAgent: (id: string | null) => void;
  showValue: boolean;
}

const NAV_ITEMS: { id: NavId; label: string; Icon: typeof IconActivity }[] = [
  { id: "activity", label: "Activity Feed", Icon: IconActivity },
  { id: "value", label: "Value", Icon: IconValue },
  { id: "agents", label: "Agents", Icon: IconAgents },
  { id: "reports", label: "Reports", Icon: IconReports },
  { id: "settings", label: "Value Ontology", Icon: IconSettings },
];

const HEALTH_COLOR: Record<AgentMeta["health"], string> = {
  green: "#3f9d6b",
  amber: "#c79a3a",
  red: "#c25b4c",
};

/** Left sidebar — logo, primary nav, agent roster with health dots. */
export function Sidebar({
  nav,
  setNav,
  agents,
  selectedAgent,
  setSelectedAgent,
  showValue,
}: SidebarProps) {
  // The Value view exists only when the value layer judged something.
  const items = NAV_ITEMS.filter((item) => item.id !== "value" || showValue);
  return (
    <aside className="ap-sidebar">
      <div className="ap-brand">
        <span className="ap-brand-mark" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
        </span>
        <span className="ap-brand-name">Agent&nbsp;Panorama</span>
      </div>

      <nav className="ap-nav">
        {items.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={"ap-nav-item" + (nav === id ? " is-active" : "")}
            onClick={() => setNav(id)}
          >
            <Icon size={17} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="ap-roster">
        <div className="ap-roster-hd">Agents</div>
        <div className="ap-roster-list">
          <button
            className={"ap-agent" + (selectedAgent === null ? " is-active" : "")}
            onClick={() => setSelectedAgent(null)}
          >
            <span
              className="ap-agent-dot"
              style={{
                background: "transparent",
                boxShadow: "inset 0 0 0 1.5px #b8b4aa",
              }}
            />
            <span className="ap-agent-name">All agents</span>
          </button>
          {Object.values(agents).map((a) => (
            <button
              key={a.id}
              className={"ap-agent" + (selectedAgent === a.id ? " is-active" : "")}
              onClick={() => setSelectedAgent(selectedAgent === a.id ? null : a.id)}
            >
              <span
                className="ap-agent-dot"
                style={{ background: HEALTH_COLOR[a.health] }}
              />
              <span className="ap-agent-name">{a.name}</span>
              <span
                className="ap-agent-accent"
                style={{ background: a.accent }}
              />
            </button>
          ))}
        </div>
      </div>

      <div className="ap-sidebar-foot">
        <div className="ap-user">
          <span className="ap-user-av">DM</span>
          <span className="ap-user-meta">
            <b>Dana Marek</b>
            <i>Operations Lead</i>
          </span>
        </div>
      </div>
    </aside>
  );
}
