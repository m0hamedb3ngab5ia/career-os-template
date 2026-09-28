// Jobs endpoint shapes, generated from the FastAPI OpenAPI schema (src/api/schema.gen.ts; services/jobs.py). The
// tracker replies (routers/tracker.py) stay hand-written.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

/** An index row plus `next_action`: the highest-priority open Action Item's "what" for this job. */
export type JobListItem = Schemas["JobListItem"];
export type JobsPage = Schemas["JobsPage"];
export type JobsTab = Schemas["JobsTab"];
export type JobsTabs = Schemas["JobsTabs"];
export type JobFacets = Schemas["JobFacets"];

export type TabKey = "active" | "review" | "applied" | "tier_a" | "all";

export interface TrackerSync {
  synced: number;
  path: string;
  pending: number | boolean | null;
}

export interface TrackerOpen {
  opened: boolean;
  path: string;
}
