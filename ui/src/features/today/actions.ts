import { parseTime } from "../../lib/dates";
import type { ActionItem } from "./types";

// Grouping, order and link handling for the "Needs you" list. Pure, so the screen and the tests share them.

// Task types that stop an application until you act (design doc 3 "Today": blocked first).
const BLOCKING = new Set(["captcha", "bot_detection", "question", "salary", "profile_gap", "qa_fail", "laptop_required", "scam_suspected"]);
const PRIO: Record<string, number> = { H: 0, M: 1, L: 2 };
const blocked = (a: ActionItem) => (BLOCKING.has(a.type) ? 0 : 1);
const prio = (a: ActionItem) => PRIO[a.priority ?? ""] ?? 3;
const due = (a: ActionItem) => parseTime(a.due)?.getTime() ?? Number.POSITIVE_INFINITY;
const byDue = (a: ActionItem, b: ActionItem) => {
  const x = due(a);
  const y = due(b);
  return x === y ? 0 : x < y ? -1 : 1;
};
const byOrder = (a: ActionItem, b: ActionItem) => blocked(a) - blocked(b) || prio(a) - prio(b) || byDue(a, b);

export interface JobGroup {
  /** null = the final "Other tasks" group (tasks with no job). */
  jobId: string | null;
  company: string;
  role: string;
  items: ActionItem[];
}

/** One group per job, tasks and groups ordered blocked → priority → due; job-less tasks last. */
export function groupByJob(items: readonly ActionItem[]): JobGroup[] {
  const groups = new Map<string | null, JobGroup>();
  for (const item of items.toSorted(byOrder)) {
    const jobId = item.job_id || null;
    let g = groups.get(jobId);
    if (!g) groups.set(jobId, (g = { jobId, company: item.company, role: item.role, items: [] }));
    g.items.push(item);
  }
  return [...groups.values()].sort((a, b) => (a.jobId === null ? 1 : 0) - (b.jobId === null ? 1 : 0));
}

/** Open tasks in priority order (blocked → priority → due). */
export const sortTasks = (items: readonly ActionItem[]): ActionItem[] => items.toSorted(byOrder);
