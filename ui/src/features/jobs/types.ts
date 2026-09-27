// Shapes of the Jobs endpoints (src/careeros/ui/services/jobs.py + the today-jobs API contract).

export interface JobListItem {
  job_id: string;
  company: string | null;
  title: string | null;
  location: string | null;
  ats: string | null;
  url: string | null;
  category: string | null;
  fit: number | null;
  tier: string | null;
  status: string | null;
  safety: string | null;
  qa_passed: boolean | number | null;
  qa_score: number | null;
  found_at: string | null;
  applied_at: string | null;
  updated_at: string | null;
  closes_at: string | null;
  /** The highest-priority open Action Item's "what" for this job. */
  next_action?: string | null;
}

export interface JobsPage {
  items: JobListItem[];
  total: number;
  next_cursor: string | null;
}

export type TabKey = "active" | "review" | "applied" | "tier_a" | "all";

export interface JobsTab {
  key: string;
  label: string;
  count: number;
}

export interface JobsTabs {
  tabs: JobsTab[];
}

export interface TrackerSync {
  synced: number;
  path: string;
  pending: number | boolean | null;
}

export interface TrackerOpen {
  opened: boolean;
  path: string;
}
