import type { Tone } from "../../kit/labels";
import { humanize } from "../../kit/labels";

// inbox-sync classes (.claude/skills/inbox-sync/SKILL.md section 3). Unknown classes: humanized, gray.
const CLASSES: Record<string, { label: string; tone: Tone }> = {
  confirmation: { label: "Confirmation", tone: "gray" },
  rejection: { label: "Rejected", tone: "red" },
  interview_invite: { label: "Interview invite", tone: "purple" },
  assessment: { label: "Assessment sent", tone: "orange" },
  offer: { label: "Offer", tone: "green" },
  recruiter_outreach: { label: "Recruiter outreach", tone: "blue" },
  other: { label: "Email", tone: "gray" },
};

export function emailClass(cls: string | null | undefined): { label: string; tone: Tone } {
  return (cls && CLASSES[cls]) || { label: cls ? humanize(cls) : "Email", tone: "gray" };
}

/** Chip tone for the next follow-up: notes you write yourself are purple, drafts teal. */
export function nextTone(kind: string): Tone {
  return kind === "post_interview_thanks" || kind === "reply_with_slot" || kind === "offer_reply" ? "purple" : "teal";
}
