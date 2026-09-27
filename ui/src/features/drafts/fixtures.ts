import type { Draft } from "./types";

// Fictional drafts in the server's shape (tests only).
export function draft(over: Partial<Draft> = {}): Draft {
  return {
    contact: "Dana Cruz",
    role: "recruiter",
    kind: "post_apply_outreach",
    channel: "email",
    to: "dana.cruz@example.com",
    verified: true,
    subject: "New Grad Engineer application",
    body: "Hi Dana,\n\nI applied this week. [SPECIFIC CONNECTION]\n\nHappy to share [MOST RELEVANT EXPERIENCE].",
    linkedin_note: null,
    linkedin_message: null,
    manual_tailor: false,
    manual_reason: null,
    sent: false,
    sent_by: null,
    mode: "verified_email",
    placeholders: ["[SPECIFIC CONNECTION]", "[MOST RELEVANT EXPERIENCE]"],
    words: 14,
    ...over,
  };
}

export const linkedinDraft = (over: Partial<Draft> = {}) =>
  draft({
    contact: "Sam Lee",
    kind: "cold_email",
    channel: "linkedin",
    to: null,
    verified: false,
    subject: null,
    body: "Hi Sam,\n\nI applied to the Software Engineer role.",
    linkedin_message: "Hi Sam,\n\nI applied to the Software Engineer role.",
    linkedin_note: "Hi Sam, I applied to the Software Engineer role at Stark Industries.",
    mode: "linkedin",
    placeholders: [],
    words: 9,
    ...over,
  });
