// GET /api/jobs/{id}: the envelope is generated from the FastAPI OpenAPI schema (src/api/schema.gen.ts;
// services/jobs.py JobDetail). The job's own files (posting.json, score.json, safety.json, qa.json,
// apply_session.json, contacts.json, status.json history, the registry YAML entries) are returned as written, so the
// schema has them as open mappings; their contents are described by hand below. The write replies stay hand-written.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type FileEntry = Schemas["FileEntry"];
export type ContactPolicy = Schemas["ContactPolicy"];
export type ActivityEntry = Schemas["ActivityEntry"];

export interface Posting {
  company?: string;
  title?: string;
  location?: string;
  remote?: boolean | null;
  url?: string;
  apply_url?: string;
  ats?: string;
  posted_at?: string | null;
  closes_at?: string | null;
}

export interface HistoryEntry {
  status: string;
  at: string;
  note?: string | null;
}

/** careeros.models.Score as written to score.json. `sub_scores` only when a scorer writes one. */
export interface Score {
  fit: number;
  tier?: string | null;
  category?: string;
  prestige?: string | null;
  hard_filter_fails?: string[];
  reasons?: string[];
  required_skills?: string[];
  matched_skills?: string[];
  missing_skills?: string[];
  salary_ok?: boolean | null;
  location_ok?: boolean | null;
  scored_at?: string;
  sub_scores?: Record<string, number>;
}

export interface SafetyFlag {
  code: string;
  level: string;
  detail?: string;
  evidence?: string[];
  at?: string;
}

export interface Safety {
  verdict: string;
  flags?: SafetyFlag[];
  runs?: number | unknown[];
}

/** qa.json from the qa-review skill (SKILL.md section 6). */
export interface Qa {
  rubric?: Record<string, { score: number; why?: string }>;
  mean?: number | null;
  pass?: boolean;
  fail_reasons?: string[];
  next_action?: string;
  threshold?: number;
  reviewed_at?: string;
}

export interface ApplyStep {
  time?: string;
  action: string;
  ok: boolean;
  note?: string;
}

export interface ApplySession {
  steps?: ApplyStep[];
  screenshots?: string[];
  outcome?: string | null;
  reason?: string;
  started?: string;
  finished?: string | null;
  tier?: string | null;
  ats?: string;
  auto_submit?: boolean;
}

export interface Contact {
  name: string;
  title?: string;
  role?: string;
  linkedin?: string;
  email?: string;
  draft_message?: string;
  sent?: boolean;
  linkedin_degree?: number | null;
  mutuals?: number | null;
}

export interface Registry {
  verified: null | { company: string; risk: string; signals: string[]; evidence: string[]; checked_at?: string };
  flagged: null | {
    company: string;
    domain?: string;
    reason?: string;
    confidence?: string;
    state?: string;
    evidence?: string[];
    expires_at?: string;
    review_note?: string;
  };
}

export type JobDetail = Omit<
  Schemas["JobDetail"],
  "posting" | "history" | "score" | "safety" | "qa" | "apply_session" | "contacts" | "registry"
> & {
  posting: Posting;
  history: HistoryEntry[];
  score: Score | null;
  safety: Safety | null;
  qa: Qa | null;
  apply_session: ApplySession | null;
  contacts: Contact[];
  registry: Registry;
};

export interface StatusReply {
  status: string;
  previous: string | null;
}

export interface QaRun {
  pass: boolean;
  summary?: { hard_fail?: number; soft_fail?: number; skipped?: number };
  fail_reasons?: string[];
  warnings?: string[];
}
