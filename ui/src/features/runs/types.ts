// JSON shapes of the Runs API (src/careeros/ui/routers/runs.py, services/runs_view.py, services/runs.py).
// TODO(openapi): replace with the generated types when they land.

export type BatchKind = "score" | "prepare";
export type StepKind = "scout" | "tracker" | "prune" | "inbox_sync";

export interface Budget {
  preset?: string;
  max_jobs?: number;
  max_minutes?: number;
}

export interface RunRecord {
  id: string;
  kind: string;
  trigger: string;
  budget?: Budget;
  status: string;
  /** running | done | failed | interrupted (a running run whose process no longer holds its lock) */
  state: string;
  stop_reason: string | null;
  detail?: string;
  started_at: string | null;
  ended_at: string | null;
  duration_s: number | null;
  counters?: Record<string, number>;
  warnings?: string[];
}

export interface Attempt {
  n: number;
  job_id: string;
  company?: string | null;
  title?: string | null;
  stage?: string;
  outcome: string;
  detail?: string;
  duration_s?: number | null;
  session_id?: string | null;
  started_at?: string | null;
}

export interface RunDetail extends RunRecord {
  attempts: Attempt[];
  log: string;
}

export interface HistoryPage {
  runs: RunRecord[];
  next_cursor: string | null;
}

export interface Step {
  name: string;
  /** skipped: a later step has output but this one has none (e.g. a cover letter the tier rule left out). */
  state: "done" | "active" | "pending" | "skipped";
}

export interface JobRow {
  job_id: string;
  company: string | null;
  title: string | null;
  state: "done" | "failed" | "active" | "queued";
  outcome: string | null;
  duration_s: number | null;
  detail: string;
  steps: Step[];
}

export interface Cap {
  cap: number;
  applied: number;
  remaining: number;
  reached: boolean;
}

export interface CurrentRun extends RunRecord {
  scheduled: boolean;
  current_job: string | null;
  used: { jobs: number; max_jobs: number | null; minutes: number | null; max_minutes: number | null };
  jobs: JobRow[];
  cap: Cap | null;
}

export interface Reason {
  code: "fresh" | "dream" | "deadline" | "fit" | "retry" | "other" | string;
  text: string;
  points: number | null;
}

export interface QueueItem {
  job_id: string;
  company: string;
  title: string;
  rank: number;
  score: number;
  fit: number | null;
  why: string;
  reasons: Reason[];
}

export interface Excluded {
  job_id: string;
  reason: string;
  company: string | null;
  title: string | null;
}

export interface Queue {
  kind: BatchKind;
  items: QueueItem[];
  total: number;
  excluded: Excluded[];
  excluded_total: number;
}

export interface Selection {
  dry_run: true;
  kind: BatchKind;
  budget: Budget;
  candidates: number;
  selected: QueueItem[];
}

export interface Started {
  kind: string;
  started: boolean;
  pid: number;
}

export interface Pause {
  paused_at: string;
  until: string | null;
  reason: string;
}

export interface CatchUp {
  created_at: string;
  kinds: Record<string, { first_missed: string | null; slots: number; last_missed?: string }>;
}

export interface ScheduleJob {
  kind: string;
  enabled: boolean;
  every_minutes: number | null;
  at: string[];
  preset: string | null;
  claude: boolean;
  next: string | null;
  last_run: string | null;
  last_status: string | null;
}

export interface Schedule {
  label: string;
  installed: boolean;
  loaded: boolean;
  last_tick: string | null;
  tick_minutes: number;
  quiet_hours: { start: string; end: string } | null;
  jobs: ScheduleJob[];
  catch_up: CatchUp | null;
  paused: Pause | null;
  inbox_ready: boolean;
}

export interface CancelResult {
  status: "idle" | "cancelling" | "already_stopping" | "refused";
  run_id?: string;
  detail?: string;
}

export interface Meta {
  stop_reasons: string[];
  clean_stops: string[];
  presets: {
    names: string[];
    values: Record<string, { max_score_jobs: number; max_prepare_jobs: number; max_minutes: number }>;
    recommended: string;
    current: string;
  };
  ui: { theme: string; undo_seconds: number; page_size: number; pause_until_tomorrow_at?: string };
}

export interface StreamLine {
  key: number;
  type: string;
  text: string;
  attempt?: number;
  error?: boolean;
}
