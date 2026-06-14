import type { ReactNode } from "react";

/** SVG glyphs for each ontology object, shared by the graph and the constellation. */
const ICON: Record<string, ReactNode> = {
  agent: (
    <>
      <rect x="4" y="5" width="16" height="13" rx="3" />
      <path d="M9 11h0M15 11h0" />
      <path d="M12 2v3" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 19c0-3.4 3-5.3 6.5-5.3s6.5 1.9 6.5 5.3" />
    </>
  ),
  goal: (
    <>
      <circle cx="12" cy="12" r="7.5" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  success_criteria: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8 12.2l2.6 2.6L16 9.4" />
    </>
  ),
  value_dimensions: (
    <>
      <path d="M4 8h16M4 16h16" />
      <circle cx="9" cy="8" r="2.2" />
      <circle cx="15" cy="16" r="2.2" />
    </>
  ),
  failure_modes: (
    <>
      <path d="M12 4.5l8 14.5H4z" />
      <path d="M12 10v4M12 17h0" />
    </>
  ),
  stakes: (
    <>
      <circle cx="9" cy="10" r="4.2" />
      <circle cx="15" cy="14" r="4.2" />
    </>
  ),
};

/** Render one object's glyph at the given size (default 17px). */
export function NodeIcon({ objectKey, size = 17 }: { objectKey: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {ICON[objectKey] ?? ICON.goal}
    </svg>
  );
}
