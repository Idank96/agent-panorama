# Agent Panorama - Frontend

The **manager-facing dashboard** for the `agent-panorama` toolkit - the front end of
the Clarity → Value → Cost story: see what your agents did, whether it was worth it,
and what it cost. A three-column light-mode UI: agent roster sidebar, a plain-English
activity feed (Clarity), and an expanded detail panel with facts, outcome, tokens, and
dollar cost. When the value layer is on, a second **Value** view surfaces per-conversation
scores, value delivered / lost, and cost per valuable conversation.

Stack: **Vite + React 18 + TypeScript** (no UI libraries; icons are inline SVG).

## Develop

```bash
npm install
npm run dev      # local dev server (Vite)
npm run build    # tsc -b && vite build (type-checks then bundles to dist/)
npm run preview  # serve the production build
npm run test     # run the vitest suite
```

Without a backend feed file, the dashboard renders **bundled demo data**, so
`npm run dev` works out of the box.

## Wiring to the backend

The Python backend (in this repo's `src/`) emits a `report.json` that this app reads
as `public/feed.json`. The mapping (`outcome → status`, `cost_usd → $`, etc.) lives in
`src/lib/loadFeed.ts`.

From the repository root, generate a fleet report in JSON:

```bash
uv run agent-panorama generate --input 'traces/*.json' --format json --output ./report
```

Then copy the output into the frontend's `public/` directory:

```bash
cp report/report.json frontend/public/feed.json
# or, from within frontend/:
npm run sync:feed
```

Reload the app - it now renders real fleet data (tokens **and** dollar cost when the
backend was run with a `model_prices` config). If `public/feed.json` is missing or
unparseable, the app silently falls back to the bundled demo data.

## Project layout

```
src/
  App.tsx              # wires nav, agent filter, search, decisions, value view
  main.tsx             # mounts <App/>, imports styles.css
  styles.css           # ported verbatim from the design bundle
  types.ts             # Status, Outcome, AgentMeta, FeedEntry, Decision
  icons.tsx            # inline SVG icon set
  data/
    agents.ts          # AGENTS registry + resolveAgent() palette fallback + STATUS
    demoFeed.ts        # bundled offline demo feed
  components/
    Sidebar.tsx        # roster + nav
    Feed.tsx           # FeedCard, AgentBadge, StatusPill, top bar
    DetailPanel.tsx    # expanded record (facts, policy, cost, value verdict)
    ValueView.tsx      # value view: scores, value delivered/lost, cost per valuable conversation
  lib/
    loadFeed.ts        # fetch feed.json → FeedEntry[]; demo fallback
    loadFeed.test.ts   # vitest unit tests for the mapping
```
