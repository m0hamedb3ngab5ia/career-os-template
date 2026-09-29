import { STOP_REASONS, describeCode, humanize, type Tone } from "../../kit/labels";
import { formatClock, formatNumber } from "../../lib/format";
import type { Reason, RunRecord, ScheduleJob } from "./types";

// Plain-language names for run kinds, triggers and the Start a run choices (Runs artboard).

export const KIND_LABELS: Record<string, string> = {
  scout: "Scout",
  score: "Score",
  prepare: "Prepare",
  inbox_sync: "Inbox sync",
  tracker: "Tracker",
  prune: "Prune",
};

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "Run";
  return KIND_LABELS[kind] ?? humanize(kind);
}

export const TRIGGER_LABELS: Record<string, string> = {
  manual: "manual",
  schedule: "scheduled",
  catch_up: "catch-up",
};

export function triggerLabel(trigger: string | null | undefined): string {
  if (!trigger) return "";
  return TRIGGER_LABELS[trigger] ?? humanize(trigger).toLowerCase();
}

export type StartKind = "scout" | "score" | "prepare" | "inbox" | "tracker";

export const START_KINDS: { value: StartKind; label: string; note: string }[] = [
  { value: "scout", label: "Scout", note: "Checks every board. Free: no Claude usage." },
  { value: "score", label: "Score", note: "Ranks Found jobs, then scores the top ones with /score-job." },
  { value: "prepare", label: "Prepare", note: "Runs /prepare-job on the best scored jobs: tailor, cover letter, QA." },
  { value: "inbox", label: "Inbox", note: "Reads Gmail for replies and interview invites." },
  { value: "tracker", label: "Tracker", note: "Rebuilds and exports JobTracker.xlsx." },
];

export function isStartKind(v: string | null): v is StartKind {
  return START_KINDS.some((k) => k.value === v);
}

// What each stop reason means and what to do, from docs/UI.md "Stop-reason chips". The label and tone come
// from the kit (kit/labels.ts); a code the frontend does not know still renders, gray, with no fix text.
export const STOP_FIX: Record<string, string> = {
  completed: "Nothing left in the queue.",
  budget_reached: "The preset's job count is done; the rest wait for the next run.",
  time_budget: "The preset's minutes are spent; the job in flight was cut at the budget.",
  daily_cap: "Prepared jobs fill today's apply cap.",
  paused: "Stopped by Pause all.",
  cancelled: "Stopped by you.",
  usage_limit: "Subscription limit reached; it retries at the next slot.",
  auth_required: "Run claude and /login (or /mcp for a required MCP server).",
  permission_denied: "A skill needed a tool missing from llm.allowed_tools.",
  timeout: "One skill call ran past its timeout; often a login or prompt wait.",
  consecutive_failures: "3 jobs failed in a row; open the attempts.",
  doctor_failed: "The setup check found problems; open Settings to fix them.",
  error: "The run failed; open the attempt and run.log.",
  interrupted: "The run's process stopped without recording why.",
};

/** The chip code for a run: running, interrupted, or its stop reason. */
export function runChipCode(run: Pick<RunRecord, "state" | "stop_reason">): string | null {
  if (run.state === "running") return "running";
  if (run.state === "interrupted") return "interrupted";
  return run.stop_reason;
}

export function runTone(run: Pick<RunRecord, "state" | "stop_reason">): Tone {
  return describeCode(STOP_REASONS, runChipCode(run)).tone;
}

/** Orange chips need the candidate: their fix text is shown under the row. */
export function needsYou(run: Pick<RunRecord, "state" | "stop_reason">): boolean {
  return runTone(run) === "orange";
}

const REASON_TONES: Record<string, Tone> = {
  fresh: "blue",
  dream: "purple",
  deadline: "orange",
  fit: "green",
  retry: "orange",
};

export function reasonTone(r: Reason): Tone {
  if (r.code === "fresh" && !r.points) return "gray";
  return REASON_TONES[r.code] ?? "gray";
}

export function reasonText(r: Reason, locale?: string): string {
  const text = r.text ? r.text[0]!.toUpperCase() + r.text.slice(1) : "";
  if (r.points == null || r.points === 0) return text;
  return `${text} ${r.points > 0 ? "+" : ""}${formatNumber(r.points, locale)}`;
}

export const SCHEDULE_NAMES: Record<string, string> = {
  scout: "Scout",
  inbox_sync: "Inbox sync",
  score: "Score",
  prepare: "Prepare",
  prune: "Prune + storage check",
};

/** "Every 3 h", "Every 7 days", "At 1:00 AM", "At 8:00 AM and 6:00 PM", plus the preset. */
export function cadence(job: ScheduleJob, locale?: string): string {
  let when = "";
  if (job.at.length) {
    const times = job.at.map((t) => formatClock(t, locale));
    when = `At ${new Intl.ListFormat(locale, { type: "conjunction" }).format(times)}`;
  } else if (job.every_minutes) {
    const m = job.every_minutes;
    when =
      m % 1440 === 0 && m >= 1440
        ? `Every ${formatNumber(m / 1440, locale)} ${m === 1440 ? "day" : "days"}`
        : m % 60 === 0
          ? `Every ${formatNumber(m / 60, locale)} h`
          : `Every ${formatNumber(m, locale)} min`;
  }
  const extra = job.kind === "scout" || job.kind === "prune" ? "free, no Claude usage" : "";
  const preset = job.preset ? `${humanize(job.preset)} budget` : "";
  return [when, preset, extra].filter(Boolean).join(" · ");
}
