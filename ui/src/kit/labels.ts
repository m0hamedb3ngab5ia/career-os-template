// Plain-language labels and colour tones for every code the backend writes. Keys are the exact codes from
// src/careeros/models.py (statuses, action types, needs, priority), safety verdicts, and the runner's stop
// reasons (src/careeros/runs/runner.py). Unknown codes still render: gray, with a humanized label.

export type Tone = "green" | "orange" | "red" | "purple" | "blue" | "teal" | "gray";
export interface CodeInfo {
  label: string;
  tone: Tone;
}
export type CodeTable = Readonly<Record<string, CodeInfo>>;

export const STATUSES: CodeTable = {
  found: { label: "Found", tone: "gray" },
  scored: { label: "Scored", tone: "gray" },
  skipped: { label: "Skipped", tone: "gray" },
  queued: { label: "Queued", tone: "blue" },
  prepared: { label: "Prepared", tone: "blue" },
  needs_review: { label: "Needs review", tone: "orange" },
  applied: { label: "Applied", tone: "teal" },
  screening: { label: "Screening", tone: "purple" },
  interview: { label: "Interview", tone: "purple" },
  offer: { label: "Offer", tone: "green" },
  rejected: { label: "Rejected", tone: "red" },
  withdrawn: { label: "Withdrawn", tone: "gray" },
  ghosted: { label: "Ghosted", tone: "gray" },
};

export const SAFETY: CodeTable = {
  pass: { label: "Pass", tone: "green" },
  review: { label: "Review", tone: "orange" },
  block: { label: "Block", tone: "red" },
  skip: { label: "Skip", tone: "gray" },
};

export const TIERS: CodeTable = {
  A: { label: "A", tone: "purple" },
  B: { label: "B", tone: "blue" },
  C: { label: "C", tone: "gray" },
};

export const PRIORITIES: CodeTable = {
  H: { label: "High", tone: "red" },
  M: { label: "Medium", tone: "orange" },
  L: { label: "Low", tone: "gray" },
};

export const NEEDS: CodeTable = {
  laptop: { label: "Laptop", tone: "gray" },
  phone: { label: "Phone", tone: "gray" },
  anytime: { label: "Anytime", tone: "gray" },
};

export const ACTION_TYPES: CodeTable = {
  review: { label: "Review", tone: "gray" },
  scam_suspected: { label: "Possible scam", tone: "gray" },
  captcha: { label: "Captcha", tone: "gray" },
  question: { label: "Question", tone: "gray" },
  send_linkedin: { label: "LinkedIn message", tone: "gray" },
  profile_gap: { label: "Profile gap", tone: "gray" },
  bot_detection: { label: "Bot check", tone: "gray" },
  qa_fail: { label: "QA failed", tone: "gray" },
  salary: { label: "Salary", tone: "gray" },
  send_email: { label: "Email", tone: "gray" },
  laptop_required: { label: "Needs laptop", tone: "gray" },
  ghost_job: { label: "Possible ghost job", tone: "gray" },
  other: { label: "Other", tone: "gray" },
};

// Wording from docs/UI.md "Stop-reason chips": green = the run did its job, orange = it needs you.
export const STOP_REASONS: CodeTable = {
  completed: { label: "Done", tone: "green" },
  budget_reached: { label: "Job budget used", tone: "green" },
  time_budget: { label: "Time budget used", tone: "green" },
  daily_cap: { label: "Daily cap reached", tone: "green" },
  paused: { label: "Paused", tone: "gray" },
  cancelled: { label: "Cancelled", tone: "gray" },
  usage_limit: { label: "Usage limit", tone: "orange" },
  busy: { label: "Busy", tone: "orange" },
  auth_required: { label: "Login needed", tone: "orange" },
  permission_denied: { label: "Tool not allowed", tone: "orange" },
  timeout: { label: "Job timed out", tone: "orange" },
  consecutive_failures: { label: "Too many failures", tone: "orange" },
  doctor_failed: { label: "Setup check failed", tone: "orange" },
  error: { label: "Failed", tone: "orange" },
  running: { label: "Running", tone: "blue" },
  interrupted: { label: "Interrupted", tone: "gray" },
};

// Design doc 2.4 wording, keyed like the tables above. Slices 3-9 switch pages over to it; tone stays in the tables.
export const HUMAN = {
  status: {
    found: "New", scored: "Scored", queued: "Ready to prepare", prepared: "Ready to apply",
    needs_review: "Needs your review", skipped: "Not a fit",
  },
  tier: { A: "Top choice", B: "Good match", C: "Stretch" },
  safety: { pass: "Company verified", review: "Check company", block: "Blocked" },
  action: {
    captcha: "Solve a verification check", bot_detection: "Solve a verification check",
    question: "Answer application questions", salary: "Decide a salary answer",
    profile_gap: "Add missing experience to your profile", laptop_required: "Finish on your laptop",
    qa_fail: "Review tailored resume", scam_suspected: "Check this company is real",
    ghost_job: "Posting may be stale",
    other: "Automation couldn't finish this job — retry or finish by hand",
  },
  preset: { small: "10 jobs", medium: "25 jobs", large: "50 jobs", max: "All jobs" },
  qa: {
    keyword_coverage: "Resume misses key skills from this role",
    numbers_consistent: "Resume and cover letter disagree on a detail",
    employer_title_consistent: "Resume and cover letter disagree on a detail",
    confidential_terms: "A private term appeared in a document",
  },
  stop: { auth_required: "Sign-in needed", usage_limit: "Claude usage limit reached" },
  // Terms with no code table.
  term: {
    "score run": "Score jobs", "prepare run": "Prepare documents", "apply run": "Fill application",
    "dry run": "Preview", runs: "Automation", "action item": "task", scout: "Job discovery",
    tick: "Automation schedule", schedule: "Automation schedule", "catch-up": "Missed runs",
    "qa-review fail": "Documents need review",
    "tier a": "Top choice (always submitted by you)",
  },
} as const;

// Count-aware wording for `question` ("Answer N application questions") and QA `keyword_coverage`.
export const questionsLabel = (n: number) => `Answer ${n} application question${n === 1 ? "" : "s"}`;
export const keywordCoverageLabel = (n: number) => `Resume misses ${n} key skill${n === 1 ? "" : "s"} from this role`;

export function humanize(code: string): string {
  const words = code.replace(/[_-]+/g, " ").trim().toLowerCase();
  return words ? words[0]!.toUpperCase() + words.slice(1) : "—";
}

export function describeCode(table: CodeTable, code: string | null | undefined): CodeInfo {
  if (!code) return { label: "—", tone: "gray" };
  return table[code] ?? { label: humanize(code), tone: "gray" };
}

// The one source of task text for Pipeline, Apply session and Needs you: dev codes and raw tool text → plain words.
const TASK_TEXT: Record<string, string> = {
  ...HUMAN.action,
  review: "Review and submit the application",
  tier_a_review: "Review resume + cover letter",
  send_linkedin: "Send a LinkedIn message",
  send_email: "Send an email",
};

/** Raw tool/tracker text in plain words: known ids mapped, internal paths and codes dropped. */
export function plainText(raw: string): string {
  const t = raw.trim();
  if (/chrome mcp|claude-in-chrome/i.test(t)) return "Connect Chrome: the browser extension wasn't reachable";
  const gap = /(\w[\w ]*?) bullets? (?:are|is) placeholders?/i.exec(t);
  if (gap) return `Add real ${gap[1]!.trim()} bullets to your profile`;
  const code = /^([a-z]+_[a-z_]+)\b/.exec(t)?.[1];
  if (code && TASK_TEXT[code]) return TASK_TEXT[code]!;
  if (/^[a-z]+(_[a-z]+)+$/.test(t)) return humanize(t);
  return t.replace(/\S*\.claude\/skills\/\S*/g, "").replace(/\s{2,}/g, " ").trim() || "A task needs you";
}

/** A task's text from its type (Action Item type or tier_a_review…) and its raw description. */
export function taskText(type: string | null | undefined, what?: string | null): string {
  if (what?.trim()) return plainText(what);
  return (type && TASK_TEXT[type]) || TASK_TEXT.other!;
}
