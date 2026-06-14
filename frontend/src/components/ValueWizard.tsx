import { useEffect, useRef, useState } from "react";
import type { BlueprintObject } from "../types";
import type { EditableDef } from "../lib/valueConfig";
import { wizardProgress, type WizardProgress } from "../lib/wizardProgress";
import {
  type InterviewStep,
  type InterviewTurn,
  advanceInterview,
  answerSummary,
  applySuggestion,
  defToWire,
  suggestOptions,
} from "../lib/valueInterview";
import { Chips } from "./ValueFields";
import { PropertyControl } from "./PropertyControl";
import { ValueConstellation } from "./ValueConstellation";

interface ValueWizardProps {
  agentName: string;
  blueprint: BlueprintObject[];
  initial: EditableDef;
  onComplete: (def: EditableDef) => void;
  onCancel: () => void;
}

interface Snapshot {
  step: InterviewStep;
  def: EditableDef;
  transcript: InterviewTurn[];
}

const cloneDef = (def: EditableDef): EditableDef => ({
  domain: def.domain,
  servedUser: def.servedUser,
  userGoal: def.userGoal,
  successCriteria: [...def.successCriteria],
  dimensions: def.dimensions.map((d) => ({ ...d })),
  failureModes: [...def.failureModes],
  stakesGood: def.stakesGood,
  stakesBad: def.stakesBad,
});

/**
 * The guided value-definition interview: one blueprint-driven question at a time
 * in the left panel, rendered beside the live constellation map and a progress
 * rail so the picture visibly fills in as the manager answers. The server picks
 * the next gap; Back re-shows the previous question, pre-filled, via a history stack.
 */
export function ValueWizard({
  agentName,
  blueprint,
  initial,
  onComplete,
  onCancel,
}: ValueWizardProps) {
  const [def, setDef] = useState<EditableDef>(() => cloneDef(initial));
  const [step, setStep] = useState<InterviewStep | null>(null);
  const [transcript, setTranscript] = useState<InterviewTurn[]>([]);
  const [history, setHistory] = useState<Snapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [suggesting, setSuggesting] = useState(false);
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  const advance = async (nextDef: EditableDef, nextTranscript: InterviewTurn[]) => {
    setLoading(true);
    const res = await advanceInterview({
      agent_name: agentName,
      current: defToWire(nextDef),
      transcript: nextTranscript,
    });
    setLoading(false);
    if (!res) {
      setFailed(true);
      return;
    }
    setStep(res);
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    advance(initial, []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const back = () => {
    setHistory((h) => {
      if (h.length === 0) return h;
      const last = h[h.length - 1];
      setStep(last.step);
      setDef(cloneDef(last.def));
      setTranscript(last.transcript);
      return h.slice(0, -1);
    });
  };

  if (failed) return <WizardError onCancel={onCancel} />;

  if (!step) {
    return (
      <WizardShell agentName={agentName} blueprint={blueprint} def={def} activeKey={null} onCancel={onCancel}>
        <p className="ap-wiz-loading">Preparing your first question…</p>
      </WizardShell>
    );
  }

  if (step.done) {
    return (
      <WizardShell agentName={agentName} blueprint={blueprint} def={def} activeKey={null} onCancel={onCancel}>
        <div className="ap-wiz-done">
          <h3>Here's how we'll measure value</h3>
          <p className="ap-wiz-recap">{step.recap}</p>
          <div className="ap-wiz-nav">
            {history.length > 0 && (
              <button className="ap-btn ap-btn-reject" onClick={back}>
                Back
              </button>
            )}
            <button className="ap-btn ap-save-btn" onClick={() => onComplete(def)}>
              Use this definition
            </button>
          </div>
        </div>
      </WizardShell>
    );
  }

  const onContinue = () => {
    const turn: InterviewTurn = {
      field: step.field ?? "",
      prompt: step.prompt,
      answer: answerSummary(step.field, def),
    };
    setHistory((h) => [...h, { step, def: cloneDef(def), transcript }]);
    const nextTranscript = [...transcript, turn];
    setTranscript(nextTranscript);
    advance(def, nextTranscript);
  };

  const onHelp = async () => {
    setSuggesting(true);
    const options = await suggestOptions({
      agent_name: agentName,
      current: defToWire(def),
      question: { field: step.field, prompt: step.prompt },
    });
    setSuggesting(false);
    setStep({ ...step, suggestions: options });
  };

  const pick = (option: string) => setDef((d) => applySuggestion(step.field, d, option));

  return (
    <WizardShell
      agentName={agentName}
      blueprint={blueprint}
      def={def}
      activeKey={step.object_key}
      onCancel={onCancel}
    >
      <div className="ap-wiz-step">
        <h3 className="ap-wiz-q">{step.prompt}</h3>
        {step.help && <p className="ap-wiz-sub">{step.help}</p>}

        <div className="ap-wiz-input">
          <PropertyControl fieldKey={step.field ?? "domain"} def={def} setDef={setDef} autoFocus />
        </div>

        <div className="ap-suggest">
          <button className="ap-help-btn" onClick={onHelp} disabled={suggesting}>
            {suggesting ? "Thinking…" : "Help me figure out"}
          </button>
          <Chips options={step.suggestions} onPick={pick} />
        </div>

        <div className="ap-wiz-nav">
          <button
            className="ap-btn ap-btn-reject"
            onClick={() => (history.length > 0 ? back() : onCancel())}
          >
            {history.length > 0 ? "Back" : "Cancel"}
          </button>
          <button className="ap-btn ap-save-btn" onClick={onContinue} disabled={loading}>
            {loading ? "…" : "Continue"}
          </button>
        </div>
      </div>
    </WizardShell>
  );
}

function WizardShell({
  agentName,
  blueprint,
  def,
  activeKey,
  onCancel,
  children,
}: {
  agentName: string;
  blueprint: BlueprintObject[];
  def: EditableDef;
  activeKey: string | null;
  onCancel: () => void;
  children: React.ReactNode;
}) {
  const progress = wizardProgress(blueprint, def, activeKey);
  return (
    <div className="ap-wiz">
      <section className="ap-wiz-panel">
        <button className="ap-wiz-exit" onClick={onCancel} aria-label="Close">
          ×
        </button>
        <span className="ap-wiz-kicker">Guided setup</span>
        <h2 className="ap-wiz-title">Define value for {agentName}</h2>
        <div className="ap-wiz-steps">
          <span className="ap-wiz-steps-label">
            Step {progress.stepIndex} of {progress.total}
          </span>
          <div className="ap-wiz-bar">
            <i style={{ width: `${Math.round(progress.fraction * 100)}%` }} />
          </div>
        </div>
        <div className="ap-wiz-panel-body">{children}</div>
      </section>

      <div className="ap-wiz-map">
        <ValueConstellation blueprint={blueprint} def={def} progress={progress} />
      </div>

      <ProgressRail progress={progress} blueprint={blueprint} />
    </div>
  );
}

function ProgressRail({
  progress,
  blueprint,
}: {
  progress: WizardProgress;
  blueprint: BlueprintObject[];
}) {
  const labelOf = (key: string) => blueprint.find((o) => o.key === key)?.label ?? key;
  return (
    <aside className="ap-wiz-rail">
      <Ring stepIndex={progress.stepIndex} total={progress.total} fraction={progress.fraction} />
      <div className="ap-wiz-rail-cap">
        {progress.stepIndex} of {progress.total} steps complete
      </div>
      <RailSection title="Completed" keys={progress.completed} kind="done" labelOf={labelOf} />
      <RailSection
        title="In progress"
        keys={progress.active ? [progress.active] : []}
        kind="active"
        labelOf={labelOf}
      />
      <RailSection title="To do" keys={progress.todo} kind="todo" labelOf={labelOf} />
    </aside>
  );
}

function RailSection({
  title,
  keys,
  kind,
  labelOf,
}: {
  title: string;
  keys: string[];
  kind: "done" | "active" | "todo";
  labelOf: (key: string) => string;
}) {
  if (keys.length === 0) return null;
  return (
    <div className="ap-wiz-rail-sec">
      <div className="ap-wiz-rail-hd">{title}</div>
      {keys.map((key) => (
        <div className={`ap-wiz-rail-item is-${kind}`} key={key}>
          <span className="ap-wiz-rail-dot" aria-hidden>
            {kind === "done" ? "✓" : ""}
          </span>
          <span>{labelOf(key)}</span>
        </div>
      ))}
    </div>
  );
}

function Ring({
  stepIndex,
  total,
  fraction,
}: {
  stepIndex: number;
  total: number;
  fraction: number;
}) {
  const r = 26;
  const circ = 2 * Math.PI * r;
  return (
    <div className="ap-ring">
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle className="ap-ring-track" cx="34" cy="34" r={r} fill="none" />
        <circle
          className="ap-ring-fill"
          cx="34"
          cy="34"
          r={r}
          fill="none"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - fraction)}
          transform="rotate(-90 34 34)"
        />
      </svg>
      <span className="ap-ring-num">
        {stepIndex}
        <i>/{total}</i>
      </span>
    </div>
  );
}

function WizardError({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="ap-wiz-error">
      <h3 className="ap-wiz-q">Couldn't reach the guided setup</h3>
      <p className="ap-wiz-sub">
        The guided interview needs the live server. You can still define value manually.
      </p>
      <div className="ap-wiz-nav">
        <button className="ap-btn ap-save-btn" onClick={onCancel}>
          Edit manually
        </button>
      </div>
    </div>
  );
}
