// Matches src/careeros/ui/services/actions.py (GET /api/actions and the write responses).

export type Tab = "open" | "today" | "done";
export type GroupBy = "due" | "priority" | "needs";
export type SortBy = "soonest" | "priority" | "newest";
export type DueLevel = "overdue" | "soon" | "later" | "none";

export interface ActionItem {
  id: string;
  created: string | null;
  job_id: string | null;
  company: string;
  role: string;
  type: string;
  what: string;
  link: string;
  priority: string;
  needs: string;
  done: boolean;
  done_date: string | null;
  due: string | null;
  due_date_only: boolean;
  due_reason: string | null;
  bucket: string;
  level: DueLevel;
  scam_actions: boolean;
}

export interface ActionGroup {
  key: string;
  count: number;
  items: ActionItem[];
}

export interface ActionsView {
  tab: Tab;
  group: GroupBy;
  sort: SortBy;
  counts: { open: number; today: number; done: number };
  head: { overdue: number; soon: number };
  groups: ActionGroup[];
  more_done: number;
  now: string;
}

export interface WriteResult {
  ok: string[];
  queued: string[];
  missing: string[];
}

export interface BlockResult {
  company: string;
  added: boolean;
  queued: boolean;
  job_id: string;
}

export interface SafeResult {
  company: string;
  job_id: string;
  previous_status: string | null;
  registry_before: Record<string, unknown> | null;
  queued: boolean;
}

export interface NewItem {
  what: string;
  type: string;
  needs: string;
  priority: string;
  job_id?: string;
  company?: string;
  role?: string;
  link?: string;
  due?: string | null;
  due_reason?: string | null;
}
