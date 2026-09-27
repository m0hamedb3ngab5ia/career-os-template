import type { Draft } from "../drafts/types";

// GET /api/contacts (src/careeros/ui/services/contacts.py).

/** replied | sent | manual | email_draft | email_manual | linkedin_draft | no_draft (unknown values fall back to plain text). */
export type ContactMode = "replied" | "sent" | "manual" | "email_draft" | "email_manual" | "linkedin_draft" | "no_draft";

export interface ContactRow {
  job_id: string;
  company: string | null;
  job_title: string | null;
  job_status: string | null;
  name: string;
  title: string;
  linkedin: string | null;
  email: string | null;
  email_confidence: string | null;
  linkedin_degree: number | null;
  mutuals: number | null;
  sent: boolean;
  replied: string | null;
  manual: boolean;
  manual_reason: string | null;
  manual_detail: string | null;
  draft: Draft | null;
  mode: ContactMode | string;
}

export interface ContactsResponse {
  items: ContactRow[];
  linkedin_drafts: number;
  policy: { manual_if_connected: boolean; manual_if_mutuals: boolean };
}

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
