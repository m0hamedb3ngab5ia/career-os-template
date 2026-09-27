// GET /api/jobs/{id} (src/careeros/ui/services/jobs.py job_detail + the today-jobs contract) and the write replies.
import type { JobListItem } from "../jobs/types";

export interface FileEntry {
  name: string;
  size: number;
  /** Epoch seconds. */
  modified: number;
}

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

export interface ContactPolicy {
  name: string;
  role?: string;
  manual: boolean;
  reason: string | null;
  detail?: string;
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

export interface ActivityEntry {
  at: string;
  component: string;
  message: string;
}

export interface JobDetail {
  job: JobListItem | null;
  posting: Posting;
  status: string | null;
  history: HistoryEntry[];
  score: Score | null;
  safety: Safety | null;
  qa: Qa | null;
  documents: FileEntry[];
  submitted: string[];
  apply_session: ApplySession | null;
  screenshots: FileEntry[];
  contacts: Contact[];
  log: string;
  override?: string | null;
  registry?: Registry;
  outreach?: Record<string, unknown> | null;
  contacts_policy?: ContactPolicy[];
  activity?: ActivityEntry[];
}

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
