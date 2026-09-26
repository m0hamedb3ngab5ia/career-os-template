import { humanize } from "../../kit/labels";

// Plain-language names for run and schedule kinds (src/careeros/runs/schedule.py JOB_KINDS, step kinds).
const KINDS: Record<string, string> = {
  scout: "Scout",
  score: "Score",
  prepare: "Prepare",
  inbox_sync: "Inbox sync",
  prune: "Prune + storage check",
  tracker: "Tracker sync",
  apply: "Apply",
};

export const SCHEDULE_ORDER = ["scout", "score", "prepare", "inbox_sync", "prune"] as const;

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "Run";
  return KINDS[kind] ?? humanize(kind);
}

/** Recent runs name prune just "Prune": the storage check is part of the scheduled job, not every run. */
export function runKindLabel(kind: string | null | undefined): string {
  return kind === "prune" ? "Prune" : kindLabel(kind);
}
