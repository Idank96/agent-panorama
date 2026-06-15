import type { BlueprintObject } from "../types";
import type { EditableDef } from "../lib/valueConfig";
import { objectStatus } from "../lib/valueModel";
import type { WizardProgress } from "../lib/wizardProgress";
import { NodeIcon } from "./valueIcons";

interface ValueConstellationProps {
  blueprint: BlueprintObject[];
  def: EditableDef;
  progress: WizardProgress;
  /** Larger canvas with full, untruncated node content (used by the lightbox). */
  detailed?: boolean;
  /** Node-distance multiplier for detailed mode (1 = default spacing). */
  spread?: number;
}

type NodeState = "completed" | "active" | "todo";

interface Slot {
  x: number;
  y: number;
  w: number;
  h: number;
}

interface Layout {
  w: number;
  h: number;
  slots: Record<string, Slot>;
}

// Hub-and-spoke placement keyed by object: Goal at the gravitational center,
// everything else orbiting it. Independent of the blueprint's grid layout.
const COMPACT: Layout = (() => {
  const w = 580;
  const h = 460;
  const N = 152;
  const NH = 70;
  return {
    w,
    h,
    slots: {
      goal: { x: w / 2, y: h / 2, w: 188, h: 92 },
      agent: { x: 116, y: 78, w: N, h: NH },
      user: { x: w - 116, y: 78, w: N, h: NH },
      success_criteria: { x: 92, y: h / 2, w: N, h: NH },
      value_dimensions: { x: w - 92, y: h / 2, w: N, h: NH },
      failure_modes: { x: 116, y: h - 80, w: N, h: NH },
      stakes: { x: w - 116, y: h - 80, w: N, h: NH },
    },
  };
})();

// Roomier layout for the expanded lightbox so full content and edge labels have
// space - nodes pushed well apart so relation pills never collide.
const DETAILED: Layout = (() => {
  const w = 1240;
  const h = 920;
  const N = 250;
  const NH = 150;
  return {
    w,
    h,
    slots: {
      goal: { x: w / 2, y: h / 2, w: 300, h: 176 },
      agent: { x: 220, y: 150, w: N, h: NH },
      user: { x: w - 220, y: 150, w: N, h: NH },
      success_criteria: { x: 180, y: h / 2, w: N, h: NH },
      value_dimensions: { x: w - 180, y: h / 2, w: N, h: NH },
      failure_modes: { x: 220, y: h - 150, w: N, h: NH },
      stakes: { x: w - 220, y: h - 150, w: N, h: NH },
    },
  };
})();

/** Full, untruncated content lines for one object, read straight off the def. */
function nodeLines(objectKey: string, def: EditableDef): string[] {
  const list = (items: string[]) => items.map((s) => s.trim()).filter(Boolean);
  switch (objectKey) {
    case "agent":
      return list([def.domain]);
    case "user":
      return list([def.servedUser]);
    case "goal":
      return list([def.userGoal]);
    case "success_criteria":
      return list(def.successCriteria);
    case "value_dimensions":
      return def.dimensions
        .filter((d) => d.name.trim())
        .map((d) => (d.description.trim() ? `${d.name.trim()} - ${d.description.trim()}` : d.name.trim()));
    case "failure_modes":
      return list(def.failureModes);
    case "stakes":
      return list([
        def.stakesGood.trim() && `Good: ${def.stakesGood.trim()}`,
        def.stakesBad.trim() && `Bad: ${def.stakesBad.trim()}`,
      ].filter(Boolean) as string[]);
    default:
      return [];
  }
}

/** Where the segment from a slot's center toward (tx,ty) crosses its border. */
function borderPoint(slot: Slot, tx: number, ty: number): [number, number] {
  const dx = tx - slot.x;
  const dy = ty - slot.y;
  if (dx === 0 && dy === 0) return [slot.x, slot.y];
  const sx = dx !== 0 ? slot.w / 2 / Math.abs(dx) : Infinity;
  const sy = dy !== 0 ? slot.h / 2 / Math.abs(dy) : Infinity;
  const s = Math.min(sx, sy);
  return [slot.x + dx * s, slot.y + dy * s];
}

interface Edge {
  id: string;
  relation: string;
  d: string;
  lx: number;
  ly: number;
}

/** A gently curved quadratic path between two slots, plus its midpoint label spot. */
function edgeOf(from: Slot, to: Slot, relation: string, id: string, bow: number): Edge {
  const [sx, sy] = borderPoint(from, to.x, to.y);
  const [ex, ey] = borderPoint(to, from.x, from.y);
  const mx = (sx + ex) / 2;
  const my = (sy + ey) / 2;
  const dx = ex - sx;
  const dy = ey - sy;
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * bow;
  const ny = (dx / len) * bow;
  const cx = mx + nx;
  const cy = my + ny;
  return {
    id,
    relation,
    d: `M ${sx} ${sy} Q ${cx} ${cy} ${ex} ${ey}`,
    lx: mx + nx / 2,
    ly: my + ny / 2,
  };
}

const stateOf = (key: string, progress: WizardProgress): NodeState =>
  key === progress.active ? "active" : progress.completed.includes(key) ? "completed" : "todo";

/**
 * The wizard's live ontology map as a constellation: the Goal node sits at the
 * center with every other concept orbiting it, joined by gently curved relation
 * lines with floating label pills. Each node reflects its progression - completed
 * (solid, green check), active (purple, pulsing, "In progress"), or still-to-do
 * (a ghost card with placeholder lines).
 */
export function ValueConstellation({
  blueprint,
  def,
  progress,
  detailed,
  spread = 1,
}: ValueConstellationProps) {
  const base = detailed ? DETAILED : COMPACT;
  // Scale node positions and the canvas (not card size) so distances grow while
  // text stays readable; the layout stays centered and contained.
  const s = detailed ? spread : 1;
  const w = base.w * s;
  const h = base.h * s;
  const slots: Record<string, Slot> = Object.fromEntries(
    Object.entries(base.slots).map(([k, sl]) => [k, { ...sl, x: sl.x * s, y: sl.y * s }]),
  );
  const bow = detailed ? 38 : 20;
  const status = objectStatus(blueprint, def);
  const placed = blueprint.filter((obj) => slots[obj.key]);

  const edges = placed.flatMap((obj) =>
    obj.links
      .filter((link) => slots[link.to])
      .map((link) => edgeOf(slots[obj.key], slots[link.to], link.relation, `${obj.key}-${link.to}`, bow)),
  );

  return (
    <div className={"ap-constel" + (detailed ? " is-detailed" : "")} style={{ width: w, height: h }}>
      <svg className="ap-constel-links" viewBox={`0 0 ${w} ${h}`} width={w} height={h}>
        {edges.map((e) => (
          <path key={e.id} className="ap-constel-line" d={e.d} />
        ))}
      </svg>

      {edges.map((e) => (
        <span key={e.id} className="ap-constel-rel" style={{ left: e.lx, top: e.ly }}>
          {e.relation}
        </span>
      ))}

      {placed.map((obj) => {
        const slot = slots[obj.key];
        const st = stateOf(obj.key, progress);
        const isHub = obj.key === "goal";
        const lines = detailed ? nodeLines(obj.key, def) : [];
        return (
          <div
            key={obj.key}
            className={`ap-cnode is-${st}` + (isHub ? " is-hub" : "")}
            style={{ left: slot.x - slot.w / 2, top: slot.y - slot.h / 2, width: slot.w }}
          >
            <span className="ap-cnode-hd">
              <span className="ap-cnode-ico">
                <NodeIcon objectKey={obj.key} size={isHub ? 18 : 15} />
              </span>
              <span className="ap-cnode-label">{obj.label}</span>
              {st === "completed" && (
                <span className="ap-cnode-mark" aria-hidden>
                  ✓
                </span>
              )}
            </span>
            {detailed ? (
              <NodeDetail lines={lines} />
            ) : st === "todo" ? (
              <span className="ap-cnode-ghost">
                <i />
                <i />
              </span>
            ) : (
              <span className="ap-cnode-summary">{status[obj.key]?.summary || "…"}</span>
            )}
            {st === "active" && !detailed && <span className="ap-cnode-tag">In progress</span>}
          </div>
        );
      })}
    </div>
  );
}

/** Full content for a node in detailed mode: every line, untruncated. */
function NodeDetail({ lines }: { lines: string[] }) {
  if (lines.length === 0) return <span className="ap-cnode-empty">Not defined yet</span>;
  if (lines.length === 1) return <span className="ap-cnode-detail-text">{lines[0]}</span>;
  return (
    <ul className="ap-cnode-detail">
      {lines.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}
