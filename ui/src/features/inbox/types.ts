import type { Draft } from "../drafts/types";

// GET /api/inbox and /api/inbox/{job_id} (src/careeros/ui/services/inbox.py).

export interface InboxEmail {
  at: string | null;
  /** confirmation | rejection | interview_invite | assessment | offer | recruiter_outreach | other */
  class: string;
  from: string;
  status: string;
  link: string | null;
}

export interface NextStep {
  /** post_apply_outreach | status_followup | post_interview_thanks | reply_with_slot | offer_reply */
  kind: string;
  due: string | null;
  /** verified_email | linkedin | manual | always_manual | you_reply | no_draft | sent */
  mode: string;
}

export interface Availability {
  available: boolean;
  reason: string;
}

export interface InboxRow {
  job_id: string;
  company: string | null;
  title: string | null;
  status: string;
  tier: string | null;
  applied_at: string | null;
  updated_at: string | null;
  days_since_applied: number | null;
  last_email: InboxEmail | null;
  next: NextStep;
  drafts: number;
  placeholders: number;
}

export interface InboxResponse {
  items: InboxRow[];
  last_sync: string | null;
  sync: Availability;
  sending: Availability;
}

export type ThreadEvent =
  | { at: string; type: "status"; status: string; note: string | null }
  | { at: string; type: "email"; class: string; from: string; link: string | null; status: string }
  | { at: string; type: "pending_update"; status: string; note: string | null }
  | { at: string; type: "sent"; contact: string; kind: string; sent_by: string | null };

export interface InboxDetail extends InboxRow {
  thread: ThreadEvent[];
  primary: number | null;
  sync: Availability;
  sending: Availability;
}

/** The detail payload's `drafts` is the list (the list row's `drafts` is a count). */
export type InboxDetailResponse = Omit<InboxDetail, "drafts"> & { drafts: Draft[] };
