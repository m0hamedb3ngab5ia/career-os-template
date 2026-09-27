// JSON shapes of the Settings and Storage routes (src/careeros/ui/routers/settings.py, storage.py). The GET views are
// generated from the backend TypedDicts (services/settings_page.py, services/storage_view.py; ui/openapi.json ->
// src/api/schema.gen.ts); POST bodies/results (save errors, ranking preview, prune plan) stay hand-written.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

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

/** One settings field (settings_schema/model.py Field.to_dict); `control` is one of Control or a newer kind. */
export type FieldSchema = Schemas["FieldSchema"];
/** A locked row: a rule the code enforces whatever the config says. */
export type PolicyItem = Schemas["PolicyItem"];

export type Item = FieldSchema | PolicyItem;

export type GroupSchema = Schemas["GroupSchema"];
export type SectionSchema = Schemas["SectionSchema"];
/** GET /api/settings rows. */
export type SectionSummary = Schemas["SectionSummary"];

export type Values = Record<string, unknown>;

/** GET /api/settings/{section}; `files` is {file: path relative to the repo}, e.g. {pipeline: "config/pipeline.yaml"}. */
export type SectionData = Schemas["SectionData"];

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

export type Snapshot = Schemas["StorageSnapshot"];
/** GET /api/storage. */
export type StorageData = Schemas["StorageView"];
export type Recommendation = Schemas["Recommendation"];
export type RunMetrics = Schemas["RunMetrics"];
/** GET /api/advise. */
export type Advice = Schemas["Advice"];

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
