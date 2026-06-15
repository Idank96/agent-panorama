import { useEffect, useRef, useState } from "react";
import type { AgentMappingView, AgentMeta, BlueprintObject } from "../types";
import {
  type EditableConfig,
  type EditableDef,
  type LoadedValueConfig,
  blankEditableDef,
  fromEditableConfig,
  isDefinedEditable,
  loadValueConfig,
  saveValueConfig,
  slugify,
  toEditableConfig,
} from "../lib/valueConfig";
import { ValueWizard } from "./ValueWizard";
import { ValueBlueprint } from "./ValueBlueprint";

const POLL_MS = 4_000;
const DEFAULT_KEY = "__default__";

type SaveStatus = "idle" | "saving" | "saved" | "error";
type Mode = "auto" | "wizard" | "blueprint";

interface SettingsViewProps {
  agents: Record<string, AgentMeta>;
}

interface ServerMeta {
  enabled: boolean;
  agents: { key: string; name: string }[];
  mappings: Record<string, AgentMappingView>;
  ontology: { archetypes: Record<string, string>; primitives: Record<string, string> };
  blueprint: BlueprintObject[];
}

/**
 * Value Ontology - the value-definition section.
 *
 * A defined agent lands on the read-only {@link ValueBlueprint} (a strategy
 * briefing of how it creates value); the guided {@link ValueWizard} is the one
 * editing surface, reached fresh for a new agent or pre-filled to revise one.
 * Completing the wizard persists to the live server, which re-maps and re-judges.
 */
export function SettingsView({ agents }: SettingsViewProps) {
  const [draft, setDraft] = useState<EditableConfig | null>(null);
  const [meta, setMeta] = useState<ServerMeta | null>(null);
  const [serverUp, setServerUp] = useState<boolean | null>(null);
  const [readOnly, setReadOnly] = useState(false);
  const [target, setTarget] = useState<string>(DEFAULT_KEY);
  const [mode, setMode] = useState<Mode>("auto");
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [customNames, setCustomNames] = useState<Record<string, string>>({});
  const seeded = useRef(false);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      const loaded = await loadValueConfig();
      if (!active) return;
      applyServerState(loaded, { seeded, setServerUp, setReadOnly, setMeta, setDraft, setTarget });
    };
    tick();
    const interval = readOnly ? undefined : setInterval(tick, POLL_MS);
    return () => {
      active = false;
      if (interval) clearInterval(interval);
    };
  }, [readOnly]);

  if (serverUp === false) return <ReadOnlyNotice enabled={meta?.enabled ?? false} />;
  if (!draft || !meta) return <Loading />;

  const objects = listObjects(draft, meta, agents, customNames);
  const def = currentDef(draft, target);
  const mapping = target === DEFAULT_KEY ? null : (meta.mappings[target] ?? null);
  const targetLabel = objects.find((o) => o.key === target)?.label ?? "Agent";
  const wizardName = target === DEFAULT_KEY ? "your agents (fleet default)" : targetLabel;
  const surface: "intro" | "wizard" | "blueprint" = readOnly
    ? "blueprint"
    : mode === "auto"
      ? isDefinedEditable(def)
        ? "blueprint"
        : "intro"
      : mode;

  const selectTarget = (key: string) => {
    setTarget(key);
    setMode("auto");
    setStatus("idle");
  };

  const persist = async (next: EditableConfig) => {
    setStatus("saving");
    const ok = await saveValueConfig(fromEditableConfig(next));
    setStatus(ok ? "saved" : "error");
  };

  const completeWizard = (next: EditableDef) => {
    const updated = writeDef(draft, target, next);
    setDraft(updated);
    setMode("blueprint");
    void persist(updated);
  };

  const createOntology = (name: string) => {
    const key = uniqueKey(slugify(name), objects);
    setCustomNames((prev) => ({ ...prev, [key]: name }));
    setDraft((prev) => (prev ? writeDef(prev, key, blankEditableDef()) : prev));
    setTarget(key);
    setMode("wizard");
    setStatus("idle");
  };

  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Value Ontology</h1>
            <span className="ap-topbar-sub">
              Define how each agent creates value - and how it's measured
            </span>
          </div>
          {status !== "idle" && (
            <div className="ap-topbar-tools">
              <span className="ap-settings-status">{STATUS_LABEL[status]}</span>
            </div>
          )}
        </div>
      </header>

      <div className="ap-settings">
        {surface !== "blueprint" && (
          <ObjectRail objects={objects} target={target} setTarget={selectTarget} />
        )}
        <div className={"ap-settings-main" + (surface === "blueprint" ? " is-blueprint" : "")}>
          {surface === "wizard" ? (
            <ValueWizard
              key={target}
              agentName={wizardName}
              blueprint={meta.blueprint}
              initial={def}
              onComplete={completeWizard}
              onCancel={() => setMode("auto")}
            />
          ) : surface === "intro" ? (
            <IntroPanel name={wizardName} onStart={() => setMode("wizard")} />
          ) : (
            <ValueBlueprint
              agents={objects}
              target={target}
              setTarget={selectTarget}
              def={def}
              defOf={(key) => currentDef(draft, key)}
              blueprint={meta.blueprint}
              mapping={mapping}
              mappings={meta.mappings}
              ontology={meta.ontology}
              agentName={targetLabel}
              readOnly={readOnly}
              onEdit={readOnly ? undefined : () => setMode("wizard")}
              onNew={readOnly ? undefined : createOntology}
            />
          )}
        </div>
      </div>
    </main>
  );
}

const STATUS_LABEL: Record<SaveStatus, string> = {
  idle: "",
  saving: "Saving…",
  saved: "Saved - re-judging…",
  error: "Save failed - retry from the wizard",
};

/** A context key not already taken by another agent. */
function uniqueKey(base: string, objects: ObjectRow[]): string {
  const taken = new Set(objects.map((o) => o.key));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

interface ObjectRow {
  key: string;
  label: string;
  defined: boolean;
}

function listObjects(
  draft: EditableConfig,
  meta: ServerMeta,
  agents: Record<string, AgentMeta>,
  customNames: Record<string, string>,
): ObjectRow[] {
  const keys = new Set<string>([...meta.agents.map((a) => a.key), ...Object.keys(draft.contexts)]);
  const nameOf = (key: string) =>
    agents[key]?.name ?? meta.agents.find((a) => a.key === key)?.name ?? customNames[key] ?? key;
  const rows: ObjectRow[] = [...keys].sort().map((key) => ({
    key,
    label: nameOf(key),
    defined: isDefinedEditable(draft.contexts[key] ?? blankEditableDef()),
  }));
  return [
    { key: DEFAULT_KEY, label: "Fleet default", defined: isDefinedEditable(draft.default) },
    ...rows,
  ];
}

const currentDef = (draft: EditableConfig, target: string): EditableDef =>
  target === DEFAULT_KEY ? draft.default : (draft.contexts[target] ?? blankEditableDef());

const writeDef = (draft: EditableConfig, target: string, next: EditableDef): EditableConfig =>
  target === DEFAULT_KEY
    ? { ...draft, default: next }
    : { ...draft, contexts: { ...draft.contexts, [target]: next } };

/** The first agent with a complete definition, so read-only mode lands on content. */
function firstDefinedKey(config: EditableConfig): string | null {
  const ctxKey = Object.keys(config.contexts).find((k) => isDefinedEditable(config.contexts[k]));
  if (ctxKey) return ctxKey;
  return isDefinedEditable(config.default) ? DEFAULT_KEY : null;
}

function applyServerState(
  loaded: LoadedValueConfig | null,
  ctx: {
    seeded: React.MutableRefObject<boolean>;
    setServerUp: (v: boolean) => void;
    setReadOnly: (v: boolean) => void;
    setMeta: (m: ServerMeta) => void;
    setDraft: (d: EditableConfig) => void;
    setTarget: (key: string) => void;
  },
) {
  if (!loaded) {
    ctx.setServerUp(false);
    return;
  }
  const res = loaded.response;
  ctx.setServerUp(true);
  ctx.setReadOnly(!loaded.live);
  ctx.setMeta({
    enabled: res.enabled,
    agents: res.agents,
    mappings: res.mappings,
    ontology: res.ontology,
    blueprint: res.blueprint ?? [],
  });
  if (!ctx.seeded.current) {
    ctx.seeded.current = true;
    const editable = toEditableConfig(res.config);
    ctx.setDraft(editable);
    if (!loaded.live) {
      const first = firstDefinedKey(editable);
      if (first) ctx.setTarget(first);
    }
  }
}

function ObjectRail({
  objects,
  target,
  setTarget,
}: {
  objects: ObjectRow[];
  target: string;
  setTarget: (key: string) => void;
}) {
  return (
    <aside className="ap-settings-rail">
      <div className="ap-settings-rail-hd">Agents</div>
      {objects.map((o) => (
        <button
          key={o.key}
          className={"ap-settings-obj" + (target === o.key ? " is-active" : "")}
          onClick={() => setTarget(o.key)}
        >
          <span className={"ap-settings-obj-dot" + (o.defined ? " is-defined" : "")} />
          <span className="ap-settings-obj-name">{o.label}</span>
        </button>
      ))}
    </aside>
  );
}

function IntroPanel({ name, onStart }: { name: string; onStart: () => void }) {
  return (
    <div className="ap-settings-intro">
      <div className="ap-settings-intro-card">
        <h2>Define how value is measured for {name}</h2>
        <p>
          Answer a few quick questions and we'll build the value map with you - each one
          tailored to what this agent actually does. Stuck on any of them? Tap{" "}
          <b>Help me figure out</b> for suggestions. You can edit everything afterward.
        </p>
        <div className="ap-wiz-nav">
          <button className="ap-btn ap-save-btn" onClick={onStart}>
            Start guided setup
          </button>
        </div>
      </div>
    </div>
  );
}

function ReadOnlyNotice({ enabled }: { enabled: boolean }) {
  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Value Ontology</h1>
            <span className="ap-topbar-sub">Define how value is measured</span>
          </div>
        </div>
      </header>
      <div className="ap-placeholder">
        <div className="ap-placeholder-inner">
          <h2>Editing needs the live server</h2>
          <p>
            The value definition is saved by a running <code>agent-panorama serve</code>. This
            looks like the static export, so the builder is read-only here. Run the live server
            to define and persist how value is measured for each agent.
          </p>
          {enabled && <p>A value definition is currently active.</p>}
        </div>
      </div>
    </main>
  );
}

function Loading() {
  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Value Ontology</h1>
            <span className="ap-topbar-sub">Loading…</span>
          </div>
        </div>
      </header>
    </main>
  );
}
