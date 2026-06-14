import type { ValueDefinition } from "../types";
import type { EditableDef } from "./valueConfig";

const INTERVIEW_URL = "/api/value-interview";

export type InputKind = "text" | "longtext" | "list" | "dimensions";

/** One step the wizard renders, returned by the server. */
export interface InterviewStep {
  done: boolean;
  field: string | null;
  object_key: string;
  prompt: string;
  help: string;
  input_kind: InputKind;
  suggestions: string[];
  recap: string;
}

/** One answered question, sent back as history on the next step. */
export interface InterviewTurn {
  field: string;
  prompt: string;
  answer: string;
}

/** Always-object wire form of a (possibly partial) editable definition. */
export const defToWire = (def: EditableDef): ValueDefinition => {
  const custom_dimensions: Record<string, string> = {};
  for (const { name, description } of def.dimensions) {
    if (name.trim()) custom_dimensions[name.trim()] = description.trim();
  }
  return {
    domain: def.domain.trim() || null,
    user_goal: def.userGoal.trim() || null,
    success_criteria: def.successCriteria.map((c) => c.trim()).filter(Boolean),
    custom_dimensions,
    served_user: def.servedUser.trim() || null,
    failure_modes: def.failureModes.map((m) => m.trim()).filter(Boolean),
    stakes_good: def.stakesGood.trim() || null,
    stakes_bad: def.stakesBad.trim() || null,
  };
};

const joinList = (items: string[]) => items.map((c) => c.trim()).filter(Boolean).join("; ");

/** A readable one-line answer for the transcript, given the step's field. */
export const answerSummary = (field: string | null, def: EditableDef): string => {
  switch (field) {
    case "domain":
      return def.domain.trim();
    case "served_user":
      return def.servedUser.trim();
    case "user_goal":
      return def.userGoal.trim();
    case "success_criteria":
      return joinList(def.successCriteria);
    case "failure_modes":
      return joinList(def.failureModes);
    case "stakes_good":
      return def.stakesGood.trim();
    case "stakes_bad":
      return def.stakesBad.trim();
    case "custom_dimensions":
      return def.dimensions
        .filter((d) => d.name.trim())
        .map((d) => (d.description.trim() ? `${d.name} (${d.description})` : d.name))
        .join("; ");
    default:
      return "";
  }
};

const appendUnique = (items: string[], value: string) =>
  items.includes(value) ? items : [...items, value];

/** Apply a clicked suggestion to the definition, by the current field's kind. */
export const applySuggestion = (
  field: string | null,
  def: EditableDef,
  suggestion: string,
): EditableDef => {
  switch (field) {
    case "domain":
      return { ...def, domain: suggestion };
    case "served_user":
      return { ...def, servedUser: suggestion };
    case "user_goal":
      return { ...def, userGoal: suggestion };
    case "stakes_good":
      return { ...def, stakesGood: suggestion };
    case "stakes_bad":
      return { ...def, stakesBad: suggestion };
    case "success_criteria":
      return { ...def, successCriteria: appendUnique(def.successCriteria, suggestion) };
    case "failure_modes":
      return { ...def, failureModes: appendUnique(def.failureModes, suggestion) };
    case "custom_dimensions":
      return def.dimensions.some((d) => d.name === suggestion)
        ? def
        : { ...def, dimensions: [...def.dimensions, { name: suggestion, description: "" }] };
    default:
      return def;
  }
};

interface AdvanceBody {
  agent_name: string;
  current: ValueDefinition;
  transcript: InterviewTurn[];
}

/** Fetch the next interview step. Returns null when no live server is reachable. */
export const advanceInterview = async (body: AdvanceBody): Promise<InterviewStep | null> => {
  try {
    const res = await fetch(INTERVIEW_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, action: "advance" }),
    });
    if (!res.ok) return null;
    return (await res.json()) as InterviewStep;
  } catch {
    return null;
  }
};

interface SuggestBody {
  agent_name: string;
  current: ValueDefinition;
  question: { field: string | null; prompt: string };
}

/** Fetch "help me figure out" options for the current question. */
export const suggestOptions = async (body: SuggestBody): Promise<string[]> => {
  try {
    const res = await fetch(INTERVIEW_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, action: "suggest" }),
    });
    if (!res.ok) return [];
    const data = (await res.json()) as { suggestions?: string[] };
    return data.suggestions ?? [];
  } catch {
    return [];
  }
};
