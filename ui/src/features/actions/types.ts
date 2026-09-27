// JSON shapes of the Actions API (src/careeros/ui/services/actions.py).
// The GET view is generated from the backend TypedDicts (ui/openapi.json -> src/api/schema.gen.ts); write results stay hand-written.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type Tab = "open" | "today" | "done";
export type GroupBy = "due" | "priority" | "needs";
export type SortBy = "soonest" | "priority" | "newest";
export type DueLevel = "overdue" | "soon" | "later" | "none";

/** GET /api/actions (services/actions.py). The tab/group/sort/level fields arrive as plain strings. */
export type ActionItem = Schemas["ActionItem"];
export type ActionGroup = Schemas["ActionGroup"];
export type ActionsView = Schemas["ActionsPage"];

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
