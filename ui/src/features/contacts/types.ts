// GET /api/contacts (src/careeros/ui/services/contacts.py), generated from the backend TypedDicts.
import type { components } from "../../api/schema.gen";

type Schemas = components["schemas"];

/** replied | sent | manual | email_draft | email_manual | linkedin_draft | no_draft (unknown values fall back to plain text). */
export type ContactMode = "replied" | "sent" | "manual" | "email_draft" | "email_manual" | "linkedin_draft" | "no_draft";

export type ContactRow = Schemas["ContactRow"];
export type ContactsResponse = Schemas["ContactsPage"];

export interface MarkBody {
  degree?: number;
  mutuals?: number;
}

export interface MarkResult {
  job_id: string;
  name: string;
  linkedin_degree: number | null;
  mutuals: number | null;
}
