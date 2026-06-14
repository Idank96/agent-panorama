import type { EditableDef } from "../lib/valueConfig";
import { DimensionEditor, ListEditor } from "./ValueFields";

interface PropertyControlProps {
  fieldKey: string;
  def: EditableDef;
  setDef: (updater: (d: EditableDef) => EditableDef) => void;
  autoFocus?: boolean;
}

/** Bind one blueprint field to its editable-definition slice and editor. */
export function PropertyControl({ fieldKey, def, setDef, autoFocus }: PropertyControlProps) {
  switch (fieldKey) {
    case "served_user":
      return (
        <textarea
          className="ap-input ap-textarea"
          value={def.servedUser}
          autoFocus={autoFocus}
          placeholder="A frustrated customer who was charged twice"
          onChange={(e) => setDef((d) => ({ ...d, servedUser: e.target.value }))}
        />
      );
    case "user_goal":
      return (
        <textarea
          className="ap-input ap-textarea"
          value={def.userGoal}
          autoFocus={autoFocus}
          placeholder="Resolve a billing discrepancy without contacting a human"
          onChange={(e) => setDef((d) => ({ ...d, userGoal: e.target.value }))}
        />
      );
    case "stakes_good":
      return (
        <textarea
          className="ap-input ap-textarea"
          value={def.stakesGood}
          autoFocus={autoFocus}
          placeholder="Saves ~15 min of agent time and avoids a churn risk"
          onChange={(e) => setDef((d) => ({ ...d, stakesGood: e.target.value }))}
        />
      );
    case "stakes_bad":
      return (
        <textarea
          className="ap-input ap-textarea"
          value={def.stakesBad}
          autoFocus={autoFocus}
          placeholder="A wrong answer can trigger a chargeback and a complaint"
          onChange={(e) => setDef((d) => ({ ...d, stakesBad: e.target.value }))}
        />
      );
    case "success_criteria":
      return (
        <ListEditor
          items={def.successCriteria}
          placeholder="Refund processed"
          addLabel="+ Add criterion"
          onChange={(successCriteria) => setDef((d) => ({ ...d, successCriteria }))}
        />
      );
    case "failure_modes":
      return (
        <ListEditor
          items={def.failureModes}
          placeholder="Tells a customer the wrong refund amount"
          addLabel="+ Add failure mode"
          onChange={(failureModes) => setDef((d) => ({ ...d, failureModes }))}
        />
      );
    case "custom_dimensions":
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
          autoFocus={autoFocus}
          placeholder="B2B SaaS billing support"
          onChange={(e) => setDef((d) => ({ ...d, domain: e.target.value }))}
        />
      );
  }
}
