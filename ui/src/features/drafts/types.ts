// One outreach.json draft as the server sends it (src/careeros/ui/services/inbox.py: draft_view), generated from the backend TypedDict.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

export type DraftMode = "sent" | "always_manual" | "manual" | "verified_email" | "email_manual" | "linkedin";

/** One outreach.json draft (services/inbox.py: InboxDraft). */
export type Draft = Schemas["InboxDraft"];
