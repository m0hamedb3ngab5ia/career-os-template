import type { Meta } from "../../api/meta";
import type { JobListItem } from "./types";

// Fictional companies only.
export const META: Meta = {
  statuses: ["found", "scored", "queued", "prepared", "needs_review", "applied", "screening", "interview", "offer",
    "rejected", "withdrawn", "ghosted", "skipped"],
  tiers: ["A", "B", "C"],
  priorities: ["H", "M", "L"],
  action_types: ["review", "other"],
  action_needs: ["laptop", "phone", "anytime"],
  safety_verdicts: ["pass", "review", "block", "skip"],
  stop_reasons: ["completed"],
  clean_stops: ["completed"],
  presets: { names: ["medium"], values: {}, recommended: "medium", current: "medium" },
  pipeline: {
    columns: [
      { name: "Found", statuses: ["found", "scored"] },
      { name: "Queued", statuses: ["queued", "prepared"] },
      { name: "Needs review", statuses: ["needs_review"] },
      { name: "Applied", statuses: ["applied"] },
      { name: "Screening · Interview", statuses: ["screening", "interview"] },
      { name: "Offer", statuses: ["offer"] },
    ],
    closed: ["rejected", "withdrawn", "ghosted", "skipped"],
  },
  ui: { theme: "system", undo_seconds: 8, page_size: 2 },
};

export function job(over: Partial<JobListItem> & { job_id: string }): JobListItem {
  return {
    company: "Northwind Labs",
    title: "Software Engineer",
    location: "Springfield",
    ats: "greenhouse",
    url: "https://example.com/jobs/1",
    category: "swe",
    fit: 80,
    tier: "B",
    status: "queued",
    safety: "pass",
    qa_passed: null,
    qa_score: null,
    found_at: "2026-09-20T09:00:00",
    applied_at: null,
    updated_at: "2026-09-21T09:00:00",
    closes_at: null,
    next_action: null,
    ...over,
  };
}

export const JOBS: JobListItem[] = [
  job({ job_id: "nw01", company: "Northwind Labs", fit: 91, tier: "A", status: "needs_review", qa_score: 8.6,
    next_action: "You submit (Tier A)" }),
  job({ job_id: "gx02", company: "Globex Analytics", title: "Data Engineer", location: "Remote", fit: 84,
    status: "applied", applied_at: "2026-09-22T10:00:00", ats: "lever" }),
  job({ job_id: "in03", company: "Initech", fit: 70, tier: null, status: "on_hold", safety: "mystery", ats: null }),
];

export const TABS_REPLY = {
  tabs: [
    { key: "active", label: "Active", count: 59 },
    { key: "review", label: "Needs review", count: 6 },
    { key: "applied", label: "Applied", count: 41 },
    { key: "tier_a", label: "Tier A", count: 9 },
    { key: "all", label: "All", count: 736 },
  ],
};
