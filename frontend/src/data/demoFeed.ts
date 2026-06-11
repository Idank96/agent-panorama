import type { FeedEntry } from "../types";

// Activity feed, newest first. Each entry carries the expanded detail payload
// rendered in the right panel: plain-English key/value facts, token cost, and
// the policy rule applied. This is the offline fallback / mockup fidelity data.
export const demoFeed: FeedEntry[] = [
  {
    id: "e1",
    agent: "scheduling",
    action: "Scheduled a meeting on June 19 at 12:00 with the CEO of Uber",
    time: "2m ago",
    fullTime: "May 31, 2026 · 9:42 AM",
    status: "completed",
    summary:
      "Found a mutually open slot and sent calendar invites to all four attendees.",
    facts: [
      ["Meeting title", "Partnership intro — Uber × Acme"],
      ["Date & time", "Thu, June 19 · 12:00–12:45 PM PT"],
      ["Attendees", "D. Khosrowshahi (Uber), J. Park, M. Lee, You"],
      ["Location", "Google Meet (link generated)"],
      ["Calendars checked", "4 of 4 available"],
    ],
    tokens: { used: 3120, cost: "$0.038" },
    policy: {
      rule: "External meetings auto-confirm",
      detail:
        "Calendar booking with external execs is permitted without approval when all internal calendars are free.",
    },
  },
  {
    id: "e2",
    agent: "support",
    action:
      "Issued refund for order #10482 (duplicate charge)",
    time: "18m ago",
    fullTime: "May 31, 2026 · 9:26 AM",
    status: "completed",
    summary:
      "Confirmed the duplicate charge, issued the refund, and logged it to the ticket.",
    facts: [
      ["Order", "#10482"],
      ["Issue", "Duplicate charge"],
      ["Refund amount", "$129.00"],
      ["Resolved", "June 5, 2026 · 11:59 PM"],
      ["Ticket record", "Updated — stage: Resolved"],
    ],
    tokens: { used: 1840, cost: "$0.022" },
    policy: {
      rule: "Standard refund dispatch",
      detail:
        "Issuing pre-approved refunds for verified duplicate charges requires no human sign-off.",
    },
  },
  {
    id: "e3",
    agent: "funding",
    action: "Sent term sheet to CustomerX Ltd. — $240K deal",
    time: "40m ago",
    fullTime: "May 31, 2026 · 9:04 AM",
    status: "completed",
    summary:
      "Generated the term sheet from the approved template and routed it for e-signature.",
    facts: [
      ["Counterparty", "CustomerX Ltd."],
      ["Deal value", "$240,000 ARR"],
      ["Contract term", "24 months"],
      ["Template", "Enterprise SaaS v3 (legal-approved)"],
      ["Sent via", "DocuSign — awaiting signature"],
    ],
    tokens: { used: 5260, cost: "$0.064" },
    policy: {
      rule: "Term sheets ≤ $250K auto-send",
      detail:
        "Deals at or below the $250K threshold using a legal-approved template may be sent without manual review.",
    },
  },
  {
    id: "e4",
    agent: "support",
    action: "Flagged order #10318 for human review",
    time: "1h ago",
    fullTime: "May 31, 2026 · 8:51 AM",
    status: "pending",
    summary:
      "Refund scoring fell inside the ambiguous band — escalating to a support lead before advancing.",
    facts: [
      ["Order", "#10318"],
      ["Issue", "Disputed charge"],
      ["Match score", "0.61 (review band: 0.55–0.70)"],
      ["Reason", "Valid claim, non-standard refund window"],
      ["Suggested action", "Approve partial refund"],
    ],
    tokens: { used: 2410, cost: "$0.029" },
    policy: {
      rule: "Ambiguous scores require human review",
      detail:
        "Orders scoring inside the review band cannot be refunded or rejected by the agent alone.",
    },
  },
  {
    id: "e5",
    agent: "scheduling",
    action: "Failed to find overlapping availability with Microsoft",
    time: "2h ago",
    fullTime: "May 31, 2026 · 7:38 AM",
    status: "failed",
    summary:
      "No common slot inside the 2-week window; partner calendar access was read-only.",
    facts: [
      ["Goal", "Q3 roadmap sync — Acme × Microsoft"],
      ["Window searched", "June 2 – June 16"],
      ["Conflict", "No overlap across 6 attendees"],
      ["Blocker", "Partner calendar read-only"],
      ["Next step", "Proposed 3 async time options"],
    ],
    tokens: { used: 4090, cost: "$0.050" },
    policy: {
      rule: "Escalate on scheduling failure",
      detail:
        "After exhausting the search window the agent must surface fallback options instead of silently retrying.",
    },
  },
  {
    id: "e6",
    agent: "ops",
    action: "Reordered 500 units of Component #A-224 from Supplier B",
    time: "3h ago",
    fullTime: "May 31, 2026 · 6:55 AM",
    status: "completed",
    summary:
      "Inventory dipped below the reorder point; placed a replenishment PO with the preferred supplier.",
    facts: [
      ["Component", "#A-224 — M3 hex standoff"],
      ["Quantity", "500 units"],
      ["Supplier", "Supplier B (preferred)"],
      ["Unit cost", "$0.42 · total $210.00"],
      ["Trigger", "Stock 180 < reorder point 250"],
    ],
    tokens: { used: 1620, cost: "$0.020" },
    policy: {
      rule: "Auto-replenish under $1K",
      detail:
        "Purchase orders below $1,000 to preferred suppliers are placed automatically when stock hits the reorder point.",
    },
  },
  {
    id: "e7",
    agent: "ops",
    action: "Detected shipping delay on PO #5512 — notified warehouse lead",
    time: "4h ago",
    fullTime: "May 31, 2026 · 5:30 AM",
    status: "completed",
    summary:
      "Carrier ETA slipped 3 days; flagged the affected order and pinged the warehouse owner.",
    facts: [
      ["Purchase order", "PO #5512"],
      ["Carrier", "FreightCo"],
      ["New ETA", "June 4 (was June 1)"],
      ["Impact", "2 assembly jobs at risk"],
      ["Notified", "M. Alvarez (Warehouse Lead)"],
    ],
    tokens: { used: 1980, cost: "$0.024" },
    policy: {
      rule: "Surface supply-chain risk",
      detail:
        "Material ETA changes beyond 48 hours are reported to the responsible owner.",
    },
  },
  {
    id: "e8",
    agent: "funding",
    action: "Drafted Q2 investor update — held for your review",
    time: "5h ago",
    fullTime: "May 31, 2026 · 4:12 AM",
    status: "pending",
    summary:
      "Compiled metrics and narrative into the investor template; awaiting approval before send.",
    facts: [
      ["Document", "Q2 2026 Investor Update"],
      ["Recipients", "11 investors (BCC)"],
      ["Highlights", "ARR +18% QoQ, churn 1.2%"],
      ["Source data", "Synced from finance dashboard"],
      ["Suggested action", "Review & approve to send"],
    ],
    tokens: { used: 6740, cost: "$0.082" },
    policy: {
      rule: "External investor comms need approval",
      detail:
        "Any communication sent to investors must be approved by a human before dispatch.",
    },
  },
];
