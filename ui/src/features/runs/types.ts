// JSON shapes of the Runs API (src/careeros/ui/routers/runs.py, services/runs_view.py, services/runs.py).
// The GET views are generated from the backend's TypedDicts (ui/openapi.json -> src/api/schema.gen.ts, docs/UI.md);
// the POST results, the ranking queue and the SSE lines stay hand-written until their routes are typed.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

/** GET /api/runs rows and GET /api/runs/{id}, /api/runs/current (services/runs_view.py). */
export type Budget = Schemas["RunBudget"];
export type RunRecord = Schemas["RunRecord"];
export type Attempt = Schemas["Attempt"];
export type RunDetail = Schemas["RunDetail"];
export type HistoryPage = Schemas["HistoryPage"];
export type Step = Schemas["JobStep"];
export type JobRow = Schemas["RunJobRow"];
export type Cap = Schemas["RunCap"];
export type CurrentRun = Schemas["CurrentRun"];
/** GET /api/schedule (services/runs_view.py: Schedule). */
export type Pause = Schemas["RunPause"];
export type CatchUp = Schemas["CatchUp"];
export type ScheduleJob = Schemas["ScheduleJob"];
export type Schedule = Schemas["Schedule"];

export type BatchKind = "score" | "prepare";
export type StepKind = "scout" | "tracker" | "prune" | "inbox_sync";

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
