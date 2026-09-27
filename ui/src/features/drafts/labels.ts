import type { Tone } from "../../kit/labels";
import { humanize } from "../../kit/labels";

// Follow-up kinds (draft-outreach step 4, templates/followup_email/README.md). Unknown kinds: humanized, gray.
const KINDS: Record<string, string> = {
  cold_email: "Intro note",
  post_apply_outreach: "After-apply note",
  status_followup: "Status follow-up",
  followup_7d: "7-day follow-up",
  followup_14d: "14-day follow-up",
  post_interview_thanks: "Thank-you after interview",
  after_rejection: "Optional reply",
  reply_with_slot: "Reply with a slot",
  offer_reply: "Reply to the offer",
};

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "Draft";
  return KINDS[kind] ?? humanize(kind);
}

// How a draft or follow-up goes out. Nothing sends on its own in this version, so no mode says "auto".
const MODES: Record<string, { label: string; tone: Tone }> = {
  always_manual: { label: "Always manual", tone: "purple" },
  manual: { label: "Manual: you tailor it", tone: "orange" },
  verified_email: { label: "Verified email", tone: "teal" },
  email_draft: { label: "Email · you send", tone: "gray" },
  linkedin: { label: "LinkedIn · you send", tone: "gray" },
  you_reply: { label: "You reply", tone: "purple" },
  sent: { label: "Sent", tone: "green" },
  no_draft: { label: "No draft yet", tone: "gray" },
};

export function modeLabel(mode: string | null | undefined): { label: string; tone: Tone } {
  return (mode && MODES[mode]) || { label: mode ? humanize(mode) : "No draft yet", tone: "gray" };
}
