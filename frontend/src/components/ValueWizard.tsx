import { useEffect, useRef, useState } from "react";
import type { EditableDef } from "../lib/valueConfig";
import {
  type InterviewStep,
  type InterviewTurn,
  advanceInterview,
  answerSummary,
  applySuggestion,
  defToWire,
  suggestOptions,
} from "../lib/valueInterview";
import { Chips, DimensionEditor, ListEditor } from "./ValueFields";

interface ValueWizardProps {
  agentName: string;
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
  userGoal: def.userGoal,
  successCriteria: [...def.successCriteria],
  dimensions: def.dimensions.map((d) => ({ ...d })),
});

/**
 * The guided value-definition interview: one adaptive question at a time.
 *
 * The server picks the next question from the answers so far; the manager can
 * ask for suggestions ("help me figure out") at any step. Past answers are kept
 * in a history stack so Back re-shows the previous question, pre-filled.
 */
export function ValueWizard({ agentName, initial, onComplete, onCancel }: ValueWizardProps) {
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

  if (failed) return <WizardError onCancel={onCancel} />;
  if (loading && !step) return <WizardShell agentName={agentName} onCancel={onCancel} body={<p className="ap-wizard-loading">Preparing your first question…</p>} />;
  if (!step) return null;

  if (step.done) {
    return (
      <WizardShell
        agentName={agentName}
        onCancel={onCancel}
        body={
          <div className="ap-wizard-done">
            <h3>Here's how we'll measure value</h3>
            <p className="ap-wizard-recap">{step.recap}</p>
            <div className="ap-wizard-actions">
              {history.length > 0 && (
                <button className="ap-btn ap-btn-reject" onClick={() => back()}>
                  Back
                </button>
              )}
              <button className="ap-btn ap-save-btn" onClick={() => onComplete(def)}>
                Use this definition
              </button>
            </div>
          </div>
        }
      />
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
  const stepNumber = transcript.length + 1;
  const estimate = Math.max(transcript.length + 2, 5);

  return (
    <WizardShell
      agentName={agentName}
      onCancel={onCancel}
      body={
        <div className="ap-wizard-step">
          <div className="ap-wizard-progress">
            Step {stepNumber} of ~{estimate}
          </div>
          <h3 className="ap-wizard-q">{step.prompt}</h3>
          {step.help && <p className="ap-wizard-help">{step.help}</p>}

          <button className="ap-help-btn" onClick={onHelp} disabled={suggesting}>
            {suggesting ? "Thinking…" : "Help me figure out"}
          </button>
          <Chips options={step.suggestions} onPick={pick} />

          <div className="ap-wizard-input">
            <StepEditor step={step} def={def} setDef={setDef} />
          </div>

          <div className="ap-wizard-actions">
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
      }
    />
  );
}

function StepEditor({
  step,
  def,
  setDef,
}: {
  step: InterviewStep;
  def: EditableDef;
  setDef: (fn: (d: EditableDef) => EditableDef) => void;
}) {
  switch (step.input_kind) {
    case "longtext":
      return (
        <textarea
          className="ap-input ap-textarea"
          value={def.userGoal}
          autoFocus
          onChange={(e) => setDef((d) => ({ ...d, userGoal: e.target.value }))}
        />
      );
    case "list":
      return (
        <ListEditor
          items={def.successCriteria}
          placeholder="Issue resolved without escalation"
          onChange={(successCriteria) => setDef((d) => ({ ...d, successCriteria }))}
        />
      );
    case "dimensions":
      return (
        <DimensionEditor
          dimensions={def.dimensions}
          onChange={(dimensions) => setDef((d) => ({ ...d, dimensions }))}
        />
      );
    default:
      return (
        <input
          className="ap-input"
          value={def.domain}
          autoFocus
          onChange={(e) => setDef((d) => ({ ...d, domain: e.target.value }))}
        />
      );
  }
}

function WizardShell({
  agentName,
  onCancel,
  body,
}: {
  agentName: string;
  onCancel: () => void;
  body: React.ReactNode;
}) {
  return (
    <div className="ap-wizard">
      <div className="ap-wizard-hd">
        <div>
          <span className="ap-wizard-kicker">Guided setup</span>
          <h2>{agentName}</h2>
        </div>
        <button className="ap-wizard-exit" onClick={onCancel} aria-label="Close">
          ×
        </button>
      </div>
      {body}
    </div>
  );
}

function WizardError({ onCancel }: { onCancel: () => void }) {
  return (
    <div className="ap-wizard">
      <div className="ap-wizard-step">
        <h3 className="ap-wizard-q">Couldn't reach the guided setup</h3>
        <p className="ap-wizard-help">
          The guided interview needs the live server. You can still define value manually.
        </p>
        <div className="ap-wizard-actions">
          <button className="ap-btn ap-save-btn" onClick={onCancel}>
            Edit manually
          </button>
        </div>
      </div>
    </div>
  );
}
