// Matches src/careeros/ui/settings_schema/model.py (Section/Group/Field/Policy.to_dict) and the Settings and
// Storage routes (src/careeros/ui/routers/settings.py, storage.py).

export type Control =
  | "switch"
  | "number"
  | "slider"
  | "select"
  | "preset_cards"
  | "text"
  | "time"
  | "time_range"
  | "tags"
  | "rule_list"
  | "reason_levels"
  | "schedule"
  | "key_value"
  | "records";

export interface FieldSchema {
  id: string;
  file: string;
  key: string;
  control: Control | string;
  label: string;
  help: string;
  default: unknown;
  recommended: boolean;
  personal: boolean;
  options: unknown[];
  strict_options: boolean;
  min: number | null;
  max: number | null;
  step: number | null;
  integer: boolean;
  nullable: boolean;
  unit: string;
  locked: boolean;
  readonly: boolean;
  note: string;
}

export interface PolicyItem {
  control: "policy";
  label: string;
  value: string;
  why: string;
  locked: true;
}

export type Item = FieldSchema | PolicyItem;

export interface GroupSchema {
  id: string;
  title: string;
  help: string;
  items: Item[];
}

export interface SectionSchema {
  id: string;
  title: string;
  help: string;
  files: string[];
  groups: GroupSchema[];
}

export interface SectionSummary {
  id: string;
  title: string;
  help: string;
  files: string[];
}

export type Values = Record<string, unknown>;

export interface SectionData {
  section: SectionSchema;
  values: Values;
  defaults: Values;
  /** {file: path relative to the repo}, e.g. {pipeline: "config/pipeline.yaml"} */
  files: Record<string, string>;
  version: string;
}

export interface SaveErrorBody {
  detail: string;
  fields: Record<string, string>;
  general: string[];
}

export interface RankedJob {
  job_id: string;
  company: string;
  title: string;
  score: number;
  why: string;
  rank: number;
}

export interface RankingPreview {
  kind: "score" | "prepare";
  items: RankedJob[];
  total: number;
}

export type StorageCategory = "postings" | "resumes_pdfs" | "screenshots" | "run_logs" | "tracker" | "other";

export interface Snapshot {
  at: string;
  trigger?: string;
  bytes: Partial<Record<StorageCategory, number>>;
  total: number;
  disk?: { total: number; free: number; free_pct: number };
}

export interface StorageData {
  bytes: Partial<Record<StorageCategory, number>>;
  total: number;
  disk: { total: number; free: number; free_pct: number };
  snapshots: Snapshot[];
  config: {
    storage: { budget_mb: number; warn_at_pct: number; disk_free_warn_pct: number };
    advisor: { advise_after_days: number; min_runs: number; window_days: number };
  };
}

export interface Recommendation {
  id: string;
  kind: "storage" | "runs" | string;
  severity: "warn" | "info" | string;
  title: string;
  why: string;
  change: { file: string; path: string; from: unknown; to: unknown } | null;
}

export interface RunMetrics {
  runs: number;
  attempts: number;
  avg_job_s: number;
  p90_job_s: number;
  failure_rate: number;
  budget_used: number;
  stops: Record<string, number>;
  prepare_share?: number | null;
}

export interface Advice {
  storage: {
    ready: boolean;
    days: number;
    need_days: number;
    current?: number;
    rate_per_day?: number;
    projection?: { "30d": number; "90d": number };
    budget?: number;
  };
  runs: { ready: boolean; min_runs: number; metrics: Partial<Record<"score" | "prepare", RunMetrics>> };
  recommendations: Recommendation[];
}

export interface PruneItem {
  job_id: string;
  action: string;
  paths: string[];
  bytes: number;
  run_id: string;
}

export interface PrunePlan {
  dry_run: true;
  items: PruneItem[];
  summary: { jobs: number; runs: number; files: number; bytes: number };
}

export function isPolicy(i: Item): i is PolicyItem {
  return i.control === "policy";
}
