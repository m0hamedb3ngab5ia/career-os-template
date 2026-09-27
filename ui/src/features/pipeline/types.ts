// Matches src/careeros/ui/services/pipeline.py (GET /api/pipeline) and job_actions.py (POST /api/jobs/{id}/status).

export type Hint =
  | { kind: "action"; type: string; due: string | null; due_reason: string | null }
  | { kind: "safety"; text: string }
  | { kind: "not_scored" }
  | { kind: "tier_a" }
  | { kind: "qa_failed" };

export interface Card {
  job_id: string;
  company: string | null;
  title: string | null;
  location: string | null;
  category: string | null;
  fit: number | null;
  tier: string | null;
  status: string;
  safety: string | null;
  qa_passed: boolean | null;
  qa_score: number | null;
  override: string | null;
  hint: Hint | null;
}

export interface Column {
  name: string;
  statuses: string[];
  count: number;
  cards: Card[];
}

export interface Board {
  columns: Column[];
  closed: { count: number; by_status: Record<string, number> };
  card_limit: number;
  options: { categories: string[]; locations: { value: string; count: number }[] };
}

export interface Filters {
  tier: string;
  category: string;
  safety: string;
  location: string;
}

export interface StatusResult {
  job_id: string;
  status: string;
  previous: string | null;
}
