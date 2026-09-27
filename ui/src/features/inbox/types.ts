// GET /api/inbox and /api/inbox/{job_id} (src/careeros/ui/services/inbox.py), generated from the backend TypedDicts
// (ui/openapi.json -> src/api/schema.gen.ts).
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type InboxEmail = Schemas["InboxEmail"];
export type NextStep = Schemas["InboxNext"];
export type Availability = Schemas["InboxAvailability"];
export type InboxRow = Schemas["InboxRow"];
export type InboxResponse = Schemas["InboxPage"];
/** One thread event; `type` is status | email | pending_update | sent and the other keys depend on it. */
export type ThreadEvent = Schemas["InboxThreadEvent"];
/** The detail payload: its `drafts` is the list (the list row's `drafts` is a count). */
export type InboxDetailResponse = Schemas["InboxDetail"];
