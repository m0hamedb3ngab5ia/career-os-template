import { parseTime } from "../../lib/dates";
import { brief } from "../actions/ActionRow";
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

// Kinds whose completion the system notices (the workflow finishing closes them): no Mark done.
const DETECTED = new Set(["question", "salary", "qa_fail", "review", "profile_gap", "captcha", "bot_detection"]);

export interface TaskRow {
  title: string;
  why: string;
  cta: string;
  href: string;
  detected: boolean;
}

/** Strip file paths and CLI commands: the row speaks plain language only. */
const plain = (t: string) =>
  t.replace(/`?careeros [^`.;]*`?/gi, "").replace(/\S*\.(ya?ml|json)\b/g, "").replace(/\s+([.,;:])/g, "$1").replace(/\s{2,}/g, " ").trim();

/** One "Needs your attention" row: a one-sentence title (company inside), optional why/blocker line, one short CTA. */
export function taskRow(a: ActionItem): TaskRow {
  const job = a.job_id ? `/jobs/${encodeURIComponent(a.job_id)}` : null;
  const profile = a.type === "profile_gap";
  const detected = DETECTED.has(a.type);
  const row = (title: string, why: string, cta: string, href: string) => ({ title, why, cta, href, detected });
  const co = a.company ? `${a.company} ` : "";
  if (/chrome/i.test(a.what)) return row("Connect CareerOS to Chrome", "Required to continue browser-based applications.", "Connect", "/settings");
  if (a.type === "review") return row(`Review ${co}application`, "Approval required before submission.", "Review", job ?? "/actions");
  if (a.type === "qa_fail") return row(`Review ${co}résumé and cover letter`, "", "Review", job ?? "/actions");
  if (a.type === "question" || a.type === "salary")
    return row(`Answer ${co}application questions`, "The application can’t continue without your answers.", "Answer", job ?? "/actions");
  if (a.type === "captcha" || a.type === "bot_detection")
    return row("Solve a verification check", "The job site asked to confirm you’re a person.", "Open", job ?? "/actions");
  const b = brief(a);
  const bullet = /\badd real (\w+?)(?:_\w+)? bullets/i.exec(b.head);
  if (bullet || (profile && /placeholder/i.test(a.what))) {
    const emp = bullet?.[1] ?? (a.company && !a.job_id ? a.company : "");
    return row(`Add ${emp ? `${emp.replace(/^./, (c) => c.toUpperCase())} ` : ""}experience to your profile`, "", "Open", "/profile");
  }
  if (profile) return row(plain(b.head) || "Fill a gap in your profile", "", "Open", "/profile");
  return row(plain(b.head) || "Finish a task", plain(b.more[0] ?? a.detail ?? ""), "Open", job ?? "/actions");
}
