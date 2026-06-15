import { useEffect, useState } from "react";
import type { AgentMappingView, BlueprintObject } from "../types";
import { fallbackSummary, type EditableDef } from "../lib/valueConfig";
import { blueprintCompleteness } from "../lib/valueModel";
import { wizardProgress } from "../lib/wizardProgress";
import { ValueConstellation } from "./ValueConstellation";

/** One agent the manager has defined a value ontology for. */
export interface BlueprintAgentRow {
  key: string;
  label: string;
  defined: boolean;
}

interface ValueBlueprintProps {
  agents: BlueprintAgentRow[];
  target: string;
  setTarget: (key: string) => void;
  def: EditableDef;
  defOf: (key: string) => EditableDef;
  blueprint: BlueprintObject[];
  mapping: AgentMappingView | null;
  mappings: Record<string, AgentMappingView>;
  ontology: { archetypes: Record<string, string>; primitives: Record<string, string> };
  agentName: string;
  readOnly?: boolean;
  onEdit?: () => void;
  onNew?: (name: string) => void;
}

/**
 * The Value Blueprint - the read-only "review & organize" view a manager lands on
 * once an agent's value ontology is defined. It reframes the ontology objects as a
 * strategy briefing: an executive summary, a snapshot constellation, a plain-language
 * value narrative, and measurement / stakes / mapping cards, with a switcher across
 * the agents they have defined. Editing happens back in the guided wizard.
 */
export function ValueBlueprint({
  agents,
  target,
  setTarget,
  def,
  defOf,
  blueprint,
  mapping,
  mappings,
  ontology,
  agentName,
  readOnly = false,
  onEdit,
  onNew,
}: ValueBlueprintProps) {
  const defined = agents.filter((a) => a.defined || a.key === target);
  return (
    <div className="ap-bp">
      <AgentSwitcher agents={defined} target={target} setTarget={setTarget} onNew={onNew} />

      <div className="ap-bp-grid">
        <ExecutiveSummary agentName={agentName} def={def} blueprint={blueprint} mapping={mapping} />
        <Snapshot def={def} blueprint={blueprint} />
      </div>

      <Narrative def={def} />

      <div className="ap-bp-measure">
        <MeasureCard kind="success" title="Success criteria" items={cleanList(def.successCriteria)} />
        <DimensionsCard dimensions={def.dimensions.filter((d) => d.name.trim())} />
        <MeasureCard kind="failure" title="Failure modes" items={cleanList(def.failureModes)} />
      </div>

      <Stakes def={def} />

      <MappingCard mapping={mapping} ontology={ontology} />

      <FleetCompare
        agents={defined}
        target={target}
        setTarget={setTarget}
        defOf={defOf}
        blueprint={blueprint}
        mappings={mappings}
      />

      <footer className="ap-bp-cta">
        <span className="ap-bp-cta-status">✓ Value definition complete</span>
        {readOnly ? (
          <span className="ap-bp-cta-readonly">
            Read-only demo - run <code>agent-panorama serve</code> to define and edit your own.
          </span>
        ) : (
          <div className="ap-bp-cta-actions">
            {onEdit && (
              <button className="ap-btn ap-btn-reject" onClick={onEdit}>
                Edit ontology
              </button>
            )}
            {onNew && <NewOntologyButton onNew={onNew} />}
          </div>
        )}
      </footer>
    </div>
  );
}

const cleanList = (items: string[]) => items.map((i) => i.trim()).filter(Boolean);

function AgentSwitcher({
  agents,
  target,
  setTarget,
  onNew,
}: {
  agents: BlueprintAgentRow[];
  target: string;
  setTarget: (key: string) => void;
  onNew?: (name: string) => void;
}) {
  return (
    <div className="ap-bp-switch">
      {agents.map((a) => (
        <button
          key={a.key}
          className={"ap-bp-pill" + (a.key === target ? " is-active" : "")}
          onClick={() => setTarget(a.key)}
        >
          {a.label}
        </button>
      ))}
      {onNew && <NewOntologyButton onNew={onNew} compact />}
    </div>
  );
}

function NewOntologyButton({ onNew, compact }: { onNew: (name: string) => void; compact?: boolean }) {
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const submit = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onNew(trimmed);
    setName("");
    setNaming(false);
  };
  if (!naming) {
    return (
      <button
        className={compact ? "ap-bp-pill is-new" : "ap-btn ap-save-btn"}
        onClick={() => setNaming(true)}
      >
        {compact ? "+ New" : "New value ontology"}
      </button>
    );
  }
  return (
    <span className="ap-bp-new-form">
      <input
        className="ap-input"
        autoFocus
        value={name}
        placeholder="New agent name"
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setNaming(false);
        }}
      />
      <button className="ap-btn ap-save-btn" onClick={submit}>
        Create
      </button>
    </span>
  );
}

function ExecutiveSummary({
  agentName,
  def,
  blueprint,
  mapping,
}: {
  agentName: string;
  def: EditableDef;
  blueprint: BlueprintObject[];
  mapping: AgentMappingView | null;
}) {
  const completeness = blueprintCompleteness(blueprint, def);
  const stakesDefined = !!(def.stakesGood.trim() || def.stakesBad.trim());
  const confidence =
    mapping && mapping.source !== "default" ? Math.round(mapping.archetype_confidence * 100) : null;
  return (
    <section className="ap-bp-exec">
      <div className="ap-bp-exec-hd">
        <h2>{agentName}</h2>
        <span className="ap-bp-complete">
          <b>{completeness}%</b> defined
        </span>
      </div>
      <p className="ap-bp-exec-sentence">{fallbackSummary(def)}</p>
      <dl className="ap-bp-metrics">
        <Metric label="Success criteria" value={cleanList(def.successCriteria).length} />
        <Metric label="Value dimensions" value={def.dimensions.filter((d) => d.name.trim()).length} />
        <Metric label="Failure modes" value={cleanList(def.failureModes).length} />
        <Metric label="Stakes" value={stakesDefined ? "Yes" : "No"} />
        {confidence !== null && <Metric label="Ontology confidence" value={`${confidence}%`} />}
      </dl>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="ap-bp-metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function Snapshot({ def, blueprint }: { def: EditableDef; blueprint: BlueprintObject[] }) {
  const [expanded, setExpanded] = useState(false);
  const progress = wizardProgress(blueprint, def, null);
  return (
    <section className="ap-bp-snapshot">
      <div className="ap-bp-snapshot-hd">
        Ontology snapshot <span className="ap-bp-snapshot-hint">Click to expand</span>
      </div>
      <button
        className="ap-bp-snapshot-frame"
        onClick={() => setExpanded(true)}
        aria-label="Expand ontology snapshot"
      >
        <ValueConstellation blueprint={blueprint} def={def} progress={progress} />
      </button>
      {expanded && (
        <ConstellationLightbox def={def} blueprint={blueprint} progress={progress} onClose={() => setExpanded(false)} />
      )}
    </section>
  );
}

function ConstellationLightbox({
  def,
  blueprint,
  progress,
  onClose,
}: {
  def: EditableDef;
  blueprint: BlueprintObject[];
  progress: ReturnType<typeof wizardProgress>;
  onClose: () => void;
}) {
  const [spread, setSpread] = useState(1);
  const step = (delta: number) =>
    setSpread((s) => Math.min(2, Math.max(0.7, Math.round((s + delta) * 100) / 100)));
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="ap-bp-lightbox" onClick={onClose}>
      <div className="ap-bp-lightbox-inner" onClick={(e) => e.stopPropagation()}>
        <button className="ap-bp-lightbox-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        <div className="ap-bp-lightbox-map">
          <ValueConstellation blueprint={blueprint} def={def} progress={progress} detailed spread={spread} />
        </div>
        <div className="ap-bp-zoom" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => step(-0.15)} disabled={spread <= 0.7} aria-label="Less spacing">
            −
          </button>
          <span>{Math.round(spread * 100)}%</span>
          <button onClick={() => step(0.15)} disabled={spread >= 2} aria-label="More spacing">
            +
          </button>
        </div>
      </div>
    </div>
  );
}

function Narrative({ def }: { def: EditableDef }) {
  const steps = [
    { label: "User", text: def.servedUser.trim() },
    { label: "Goal", text: def.userGoal.trim() },
    { label: "Success", text: cleanList(def.successCriteria).slice(0, 2).join(" · ") },
    { label: "Business value", text: def.stakesGood.trim() },
  ].filter((s) => s.text);
  if (steps.length === 0) return null;
  return (
    <section className="ap-bp-narrative">
      <div className="ap-bp-sec-hd">How value is created</div>
      <div className="ap-bp-chain">
        {steps.map((s, i) => (
          <div className="ap-bp-chain-step" key={s.label}>
            <div className="ap-bp-chain-card">
              <span className="ap-bp-chain-label">{s.label}</span>
              <span className="ap-bp-chain-text">{s.text}</span>
            </div>
            {i < steps.length - 1 && <span className="ap-bp-chain-arrow">↓</span>}
          </div>
        ))}
      </div>
    </section>
  );
}

function MeasureCard({
  kind,
  title,
  items,
}: {
  kind: "success" | "failure";
  title: string;
  items: string[];
}) {
  return (
    <section className={`ap-bp-card is-${kind}`}>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="ap-bp-empty">Not defined yet.</p>
      ) : (
        <ul className="ap-bp-list">
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DimensionsCard({ dimensions }: { dimensions: { name: string; description: string }[] }) {
  return (
    <section className="ap-bp-card is-dimension">
      <h3>Value dimensions</h3>
      {dimensions.length === 0 ? (
        <p className="ap-bp-empty">Not defined yet.</p>
      ) : (
        <ul className="ap-bp-dims">
          {dimensions.map((d, i) => (
            <li key={i}>
              <span className="ap-bp-dim-name">{d.name.trim()}</span>
              {d.description.trim() && <span className="ap-bp-dim-desc">{d.description.trim()}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Stakes({ def }: { def: EditableDef }) {
  const good = def.stakesGood.trim();
  const bad = def.stakesBad.trim();
  if (!good && !bad) return null;
  return (
    <section className="ap-bp-stakes">
      <div className="ap-bp-sec-hd">Stakes</div>
      <div className="ap-bp-stakes-grid">
        <div className="ap-bp-stake is-good">
          <span className="ap-bp-stake-hd">🟢 Good outcome</span>
          <p>{good || "Not defined."}</p>
        </div>
        <div className="ap-bp-stake is-bad">
          <span className="ap-bp-stake-hd">🔴 Bad outcome</span>
          <p>{bad || "Not defined."}</p>
        </div>
      </div>
    </section>
  );
}

function MappingCard({
  mapping,
  ontology,
}: {
  mapping: AgentMappingView | null;
  ontology: { archetypes: Record<string, string>; primitives: Record<string, string> };
}) {
  const [open, setOpen] = useState(false);
  const lines = mapping
    ? [
        ...Object.entries(mapping.dimension_to_primitive),
        ...Object.entries(mapping.criterion_to_primitive),
      ]
    : [];
  const real = mapping && mapping.source !== "default";
  return (
    <section className="ap-bp-mapping">
      <button className="ap-bp-mapping-toggle" onClick={() => setOpen((v) => !v)}>
        <span>{open ? "▾" : "▸"}</span> How this maps to the shared value ontology
      </button>
      {open && (
        <div className="ap-bp-mapping-body">
          {!real ? (
            <p className="ap-bp-empty">
              The shared mapping appears here once a model classifies this definition.
            </p>
          ) : (
            <>
              <div className="ap-bp-arch">
                <span className="ap-bp-arch-key">{mapping!.archetype}</span>
                <span className="ap-bp-arch-conf">
                  {Math.round(mapping!.archetype_confidence * 100)}% confident
                </span>
              </div>
              <div className="ap-bp-mapping-lines">
                {lines.map(([from, primitive]) => (
                  <div className="ap-bp-mapping-line" key={from}>
                    <span>{from}</span>
                    <span className="ap-bp-mapping-arrow">→</span>
                    <span className="ap-bp-mapping-to" title={ontology.primitives[primitive] ?? ""}>
                      {primitive}
                    </span>
                  </div>
                ))}
                {lines.length === 0 && <p className="ap-bp-empty">No dimensions or criteria to map yet.</p>}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function FleetCompare({
  agents,
  target,
  setTarget,
  defOf,
  blueprint,
  mappings,
}: {
  agents: BlueprintAgentRow[];
  target: string;
  setTarget: (key: string) => void;
  defOf: (key: string) => EditableDef;
  blueprint: BlueprintObject[];
  mappings: Record<string, AgentMappingView>;
}) {
  const [compare, setCompare] = useState(false);
  return (
    <section className="ap-bp-fleet">
      <div className="ap-bp-fleet-toggle">
        <button className={!compare ? "is-active" : ""} onClick={() => setCompare(false)}>
          This agent
        </button>
        <button className={compare ? "is-active" : ""} onClick={() => setCompare(true)}>
          Compare across fleet
        </button>
      </div>
      {compare && (
        <table className="ap-bp-fleet-table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Archetype</th>
              <th>Completeness</th>
              <th>Risks</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => {
              const d = defOf(a.key);
              const m = mappings[a.key];
              return (
                <tr
                  key={a.key}
                  className={a.key === target ? "is-current" : ""}
                  onClick={() => setTarget(a.key)}
                >
                  <td>{a.label}</td>
                  <td>{m && m.source !== "default" ? m.archetype : "-"}</td>
                  <td>{blueprintCompleteness(blueprint, d)}%</td>
                  <td>{cleanList(d.failureModes).length}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
