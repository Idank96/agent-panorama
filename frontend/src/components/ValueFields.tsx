/** Shared form controls used by both the manual form and the guided wizard. */

export function Field({
  label,
  hint,
  example,
  children,
}: {
  label: string;
  hint: string;
  example?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="ap-field">
      <label className="ap-field-label">{label}</label>
      <p className="ap-field-hint">{hint}</p>
      {children}
      {example && <p className="ap-field-eg">e.g. {example}</p>}
    </div>
  );
}

export function ListEditor({
  items,
  placeholder,
  addLabel = "+ Add criterion",
  onChange,
}: {
  items: string[];
  placeholder: string;
  addLabel?: string;
  onChange: (items: string[]) => void;
}) {
  const set = (i: number, v: string) => onChange(items.map((x, j) => (j === i ? v : x)));
  const remove = (i: number) => onChange(items.filter((_, j) => j !== i));
  return (
    <div className="ap-list-editor">
      {items.map((item, i) => (
        <div className="ap-list-row" key={i}>
          <input
            className="ap-input"
            value={item}
            placeholder={placeholder}
            onChange={(e) => set(i, e.target.value)}
          />
          <button className="ap-icon-btn" onClick={() => remove(i)} aria-label="Remove">
            ×
          </button>
        </div>
      ))}
      <button className="ap-add-btn" onClick={() => onChange([...items, ""])}>
        {addLabel}
      </button>
    </div>
  );
}

export function DimensionEditor({
  dimensions,
  onChange,
}: {
  dimensions: { name: string; description: string }[];
  onChange: (dims: { name: string; description: string }[]) => void;
}) {
  const set = (i: number, patch: Partial<{ name: string; description: string }>) =>
    onChange(dimensions.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const remove = (i: number) => onChange(dimensions.filter((_, j) => j !== i));
  return (
    <div className="ap-list-editor">
      {dimensions.map((dim, i) => (
        <div className="ap-dim-row" key={i}>
          <input
            className="ap-input ap-dim-name"
            value={dim.name}
            placeholder="empathy"
            onChange={(e) => set(i, { name: e.target.value })}
          />
          <input
            className="ap-input ap-dim-desc"
            value={dim.description}
            placeholder="warmth and acknowledgement of the user's frustration"
            onChange={(e) => set(i, { description: e.target.value })}
          />
          <button className="ap-icon-btn" onClick={() => remove(i)} aria-label="Remove">
            ×
          </button>
        </div>
      ))}
      <button
        className="ap-add-btn"
        onClick={() => onChange([...dimensions, { name: "", description: "" }])}
      >
        + Add dimension
      </button>
    </div>
  );
}

/** A row of clickable suggestion chips (the wizard's "help me figure out" output). */
export function Chips({
  options,
  onPick,
}: {
  options: string[];
  onPick: (option: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    <div className="ap-chips">
      {options.map((option, i) => (
        <button key={i} className="ap-chip" onClick={() => onPick(option)}>
          + {option}
        </button>
      ))}
    </div>
  );
}
