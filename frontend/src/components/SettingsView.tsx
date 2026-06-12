import { useEffect, useRef, useState } from "react";
import type { AgentMappingView, AgentMeta, ValueConfigResponse } from "../types";
import {
  type EditableConfig,
  type EditableDef,
  blankEditableDef,
  fromEditableConfig,
  isDefinedEditable,
  loadValueConfig,
  saveValueConfig,
  toEditableConfig,
} from "../lib/valueConfig";
import { DimensionEditor, Field, ListEditor } from "./ValueFields";
import { ValueWizard } from "./ValueWizard";

const POLL_MS = 4_000;
const DEFAULT_KEY = "__default__";

type SaveStatus = "idle" | "saving" | "saved" | "error";
type Mode = "auto" | "wizard" | "form";

interface SettingsViewProps {
  agents: Record<string, AgentMeta>;
}

interface ServerMeta {
  enabled: boolean;
  agents: { key: string; name: string }[];
  mappings: Record<string, AgentMappingView>;
  ontology: { archetypes: Record<string, string>; primitives: Record<string, string> };
}

/**
 * Settings — the guided "define how value is measured" view.
 *
 * Each agent (plus a fleet default) is an "object" whose value definition the
 * manager builds through an adaptive interview (default for undefined agents)
 * or edits directly in the form. The canonical archetype/primitive layer is
 * surfaced read-only. Editing persists to the live server, which re-judges; the
 * static export has no server, so the view goes read-only there.
 */
export function SettingsView({ agents }: SettingsViewProps) {
  const [draft, setDraft] = useState<EditableConfig | null>(null);
  const [meta, setMeta] = useState<ServerMeta | null>(null);
  const [serverUp, setServerUp] = useState<boolean | null>(null);
  const [target, setTarget] = useState<string>(DEFAULT_KEY);
  const [mode, setMode] = useState<Mode>("auto");
  const [status, setStatus] = useState<SaveStatus>("idle");
  const seeded = useRef(false);

  useEffect(() => {
    let active = true;
    const tick = async () => {
      const res = await loadValueConfig();
      if (!active) return;
      applyServerState(res, { seeded, setServerUp, setMeta, setDraft });
    };
    tick();
    const interval = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  if (serverUp === false) return <ReadOnlyNotice enabled={meta?.enabled ?? false} />;
  if (!draft || !meta) return <Loading />;

  const objects = listObjects(draft, meta, agents);
  const def = currentDef(draft, target);
  const mapping = target === DEFAULT_KEY ? null : (meta.mappings[target] ?? null);
  const targetLabel = objects.find((o) => o.key === target)?.label ?? "Agent";
  const wizardName = target === DEFAULT_KEY ? "your agents (fleet default)" : targetLabel;
  const surface: "intro" | "wizard" | "form" =
    mode === "auto" ? (isDefinedEditable(def) ? "form" : "intro") : mode;

  const selectTarget = (key: string) => {
    setTarget(key);
    setMode("auto");
    setStatus("idle");
  };

  const update = (next: EditableDef) => {
    setStatus("idle");
    setDraft((prev) => (prev ? writeDef(prev, target, next) : prev));
  };

  const completeWizard = (next: EditableDef) => {
    setDraft((prev) => (prev ? writeDef(prev, target, next) : prev));
    setMode("form");
    setStatus("idle");
  };

  const onSave = async () => {
    if (!draft) return;
    setStatus("saving");
    const ok = await saveValueConfig(fromEditableConfig(draft));
    setStatus(ok ? "saved" : "error");
  };

  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Settings</h1>
            <span className="ap-topbar-sub">
              Define how value is measured — in your own words, per agent
            </span>
          </div>
          {surface === "form" && (
            <div className="ap-topbar-tools">
              <SaveButton status={status} onSave={onSave} />
            </div>
          )}
        </div>
      </header>

      <div className="ap-settings">
        <ObjectRail objects={objects} target={target} setTarget={selectTarget} />
        <div className="ap-settings-main">
          {surface === "wizard" ? (
            <ValueWizard
              key={target}
              agentName={wizardName}
              initial={def}
              onComplete={completeWizard}
              onCancel={() => setMode("auto")}
            />
          ) : surface === "intro" ? (
            <IntroPanel
              name={wizardName}
              onStart={() => setMode("wizard")}
              onManual={() => setMode("form")}
            />
          ) : (
            <>
              <div className="ap-settings-rerun">
                <button className="ap-link-btn" onClick={() => setMode("wizard")}>
                  ↺ Re-run guided setup
                </button>
              </div>
              <DefinitionForm
                title={targetLabel}
                isDefault={target === DEFAULT_KEY}
                def={def}
                onChange={update}
              />
              <MappingPanel
                mapping={mapping}
                ontology={meta.ontology}
                isDefault={target === DEFAULT_KEY}
              />
            </>
          )}
        </div>
      </div>
    </main>
  );
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
): ObjectRow[] {
  const keys = new Set<string>([...meta.agents.map((a) => a.key), ...Object.keys(draft.contexts)]);
  const nameOf = (key: string) =>
    agents[key]?.name ?? meta.agents.find((a) => a.key === key)?.name ?? key;
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

function applyServerState(
  res: ValueConfigResponse | null,
  ctx: {
    seeded: React.MutableRefObject<boolean>;
    setServerUp: (v: boolean) => void;
    setMeta: (m: ServerMeta) => void;
    setDraft: (d: EditableConfig) => void;
  },
) {
  if (!res) {
    ctx.setServerUp(false);
    return;
  }
  ctx.setServerUp(true);
  ctx.setMeta({
    enabled: res.enabled,
    agents: res.agents,
    mappings: res.mappings,
    ontology: res.ontology,
  });
  if (!ctx.seeded.current) {
    ctx.seeded.current = true;
    ctx.setDraft(toEditableConfig(res.config));
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

function IntroPanel({
  name,
  onStart,
  onManual,
}: {
  name: string;
  onStart: () => void;
  onManual: () => void;
}) {
  return (
    <div className="ap-settings-intro">
      <div className="ap-settings-intro-card">
        <h2>Define how value is measured for {name}</h2>
        <p>
          Answer a few quick questions and we'll build the definition with you — each one
          tailored to what this agent actually does. Stuck on any of them? Tap{" "}
          <b>Help me figure out</b> for suggestions. You can edit everything afterward.
        </p>
        <div className="ap-wizard-actions">
          <button className="ap-btn ap-save-btn" onClick={onStart}>
            Start guided setup
          </button>
          <button className="ap-btn ap-btn-reject" onClick={onManual}>
            Or edit manually
          </button>
        </div>
      </div>
    </div>
  );
}

function DefinitionForm({
  title,
  isDefault,
  def,
  onChange,
}: {
  title: string;
  isDefault: boolean;
  def: EditableDef;
  onChange: (def: EditableDef) => void;
}) {
  return (
    <section className="ap-settings-form">
      <div className="ap-settings-form-hd">
        <h2>{title}</h2>
        <p>
          {isDefault
            ? "Applies to every agent unless that agent has its own definition below."
            : "These fields override the fleet default for this agent."}
        </p>
      </div>

      <Field
        label="Domain"
        hint="The world this agent works in — so value is judged in your language, not a generic rubric."
        example="B2B SaaS billing support"
      >
        <input
          className="ap-input"
          value={def.domain}
          placeholder="B2B SaaS billing support"
          onChange={(e) => onChange({ ...def, domain: e.target.value })}
        />
      </Field>

      <Field
        label="What the user is trying to achieve"
        hint="The goal a conversation should accomplish. Value is judged against this, not a checklist."
        example="Resolve a billing discrepancy without contacting a human"
      >
        <textarea
          className="ap-input ap-textarea"
          value={def.userGoal}
          placeholder="Resolve a billing discrepancy without contacting a human"
          onChange={(e) => onChange({ ...def, userGoal: e.target.value })}
        />
      </Field>

      <Field
        label="Success criteria"
        hint="Concrete pass/fail tests for a good outcome. Each is reported met / not met per conversation."
        example="Refund processed · No repeat contact within 48h"
      >
        <ListEditor
          items={def.successCriteria}
          placeholder="Refund processed"
          onChange={(successCriteria) => onChange({ ...def, successCriteria })}
        />
      </Field>

      <Field
        label="Custom value dimensions"
        hint="Named qualities you want every conversation scored on, 0–10."
        example="empathy · proactiveness · first-contact resolution"
      >
        <DimensionEditor
          dimensions={def.dimensions}
          onChange={(dimensions) => onChange({ ...def, dimensions })}
        />
      </Field>
    </section>
  );
}

function MappingPanel({
  mapping,
  ontology,
  isDefault,
}: {
  mapping: AgentMappingView | null;
  ontology: { archetypes: Record<string, string>; primitives: Record<string, string> };
  isDefault: boolean;
}) {
  const [open, setOpen] = useState(false);
  const lines = mapping
    ? [
        ...Object.entries(mapping.dimension_to_primitive),
        ...Object.entries(mapping.criterion_to_primitive),
      ]
    : [];
  return (
    <section className="ap-mapping">
      <button className="ap-mapping-toggle" onClick={() => setOpen((v) => !v)}>
        <span>{open ? "▾" : "▸"}</span> How this maps to the shared value ontology
      </button>
      {open && (
        <div className="ap-mapping-body">
          {isDefault ? (
            <p className="ap-mapping-note">
              The shared mapping is computed per agent. Pick an agent on the left to see how
              its definition maps to the comparable layer.
            </p>
          ) : !mapping || mapping.source === "default" ? (
            <p className="ap-mapping-note">
              Mapping appears here once you save a definition and a model with an API key has
              classified it. Without one, this agent still gets its own report.
            </p>
          ) : (
            <>
              <div className="ap-mapping-arch">
                <span className="ap-mapping-arch-key">{mapping.archetype}</span>
                <span className="ap-mapping-arch-desc">{mapping.archetype_description}</span>
                <span className="ap-mapping-arch-conf">
                  {Math.round(mapping.archetype_confidence * 100)}% confident
                </span>
              </div>
              <div className="ap-mapping-lines">
                {lines.map(([from, primitive]) => (
                  <div className="ap-mapping-line" key={from}>
                    <span className="ap-mapping-from">{from}</span>
                    <span className="ap-mapping-arrow">→</span>
                    <span className="ap-mapping-to" title={ontology.primitives[primitive] ?? ""}>
                      {primitive}
                    </span>
                  </div>
                ))}
                {lines.length === 0 && (
                  <p className="ap-mapping-note">No dimensions or criteria to map yet.</p>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function SaveButton({ status, onSave }: { status: SaveStatus; onSave: () => void }) {
  const label =
    status === "saving"
      ? "Saving…"
      : status === "saved"
        ? "Saved — re-judging…"
        : status === "error"
          ? "Save failed — retry"
          : "Save value definition";
  return (
    <button className="ap-btn ap-save-btn" onClick={onSave} disabled={status === "saving"}>
      {label}
    </button>
  );
}

function ReadOnlyNotice({ enabled }: { enabled: boolean }) {
  return (
    <main className="ap-feed">
      <header className="ap-topbar">
        <div className="ap-topbar-row">
          <div className="ap-topbar-title">
            <h1>Settings</h1>
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
            <h1>Settings</h1>
            <span className="ap-topbar-sub">Loading…</span>
          </div>
        </div>
      </header>
    </main>
  );
}
