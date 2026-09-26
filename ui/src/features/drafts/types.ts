// One outreach.json draft as the server sends it (src/careeros/ui/services/inbox.py: draft_view).

export type DraftMode = "sent" | "always_manual" | "manual" | "verified_email" | "linkedin";

export interface Draft {
  contact: string;
  role: string;
  /** cold_email | post_apply_outreach | status_followup | post_interview_thanks (unknown kinds still render). */
  kind: string;
  channel: string;
  to: string | null;
  verified: boolean;
  subject: string | null;
  body: string;
  linkedin_note: string | null;
  linkedin_message: string | null;
  manual_tailor: boolean;
  manual_reason: string | null;
  sent: boolean;
  sent_by: string | null;
  sent_date?: string | null;
  mode: DraftMode | string;
  placeholders: string[];
  words: number;
}
