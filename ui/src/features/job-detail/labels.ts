import { humanize, type CodeTable } from "../../kit/labels";

// Plain-language names for safety flag codes (src/careeros/safety/{scam,ghost,registry}.py). Unknown codes humanize.
export const FLAG_LABELS: Record<string, string> = {
  COMPANY_CONTRADICTIONS: "Company details don’t add up",
  COMPANY_NOT_YET_CHECKED: "Company check",
  COMPANY_SPARSE_PUBLIC_FOOTPRINT: "Little public trace of the company",
  FIELD_CREDENTIALS: "Form asks for passwords or logins",
  FIELD_PAYMENT: "Form asks for payment details",
  FIELD_REMOTE_ACCESS: "Form asks for remote access",
  FIELD_SENSITIVE_PRE_OFFER: "Sensitive data asked before an offer",
  GHOST_AGGREGATOR_ONLY: "Only listed on job aggregators",
  GHOST_HIRING_FREEZE: "Hiring freeze reported",
  GHOST_OLD_POST: "Old posting",
  GHOST_RECENT_LAYOFFS: "Recent layoffs",
  GHOST_REPOSTED: "Reposted many times",
  GHOST_STALE_NO_ACTIVITY: "No recent activity",
  SCAM_APPLY_DOMAIN_UNRECOGNIZED: "Apply link on an unknown domain",
  SCAM_BRAND_DOMAIN_MISMATCH: "Domain doesn’t match the brand",
  SCAM_CHAT_ONLY_INTERVIEW: "Chat-only interview",
  SCAM_FLAGGED_BEFORE: "Flagged before",
  SCAM_FREE_EMAIL_RECRUITER: "Recruiter uses a free email address",
  SCAM_NO_INTERVIEW: "Offer without an interview",
  SCAM_PAYMENT_REQUEST: "Asks you to pay",
  SCAM_REMOTE_ACCESS_REQUEST: "Asks for remote access to your computer",
  SCAM_SALARY_IMPLAUSIBLE: "Salary too good to be true",
};

export function flagLabel(code: string): string {
  return FLAG_LABELS[code] ?? humanize(code);
}

export const FLAG_LEVELS: CodeTable = {
  info: { label: "Info", tone: "gray" },
  review: { label: "Review", tone: "orange" },
  block: { label: "Block", tone: "red" },
  skip: { label: "Skip", tone: "gray" },
};

// qa-review rubric keys (SKILL.md section 6).
export const RUBRIC_LABELS: Record<string, string> = {
  relevance: "Relevance",
  specificity: "Specificity",
  voice_match: "Voice",
  zero_fabrication: "Truthfulness",
  ats_safety: "ATS safety",
  bullet_strength: "Bullet strength",
};

export const OVERRIDES = ["", "A", "B", "C", "skip", "manual"] as const;
export const OVERRIDE_LABELS: Record<string, string> = {
  "": "None",
  A: "Tier A",
  B: "Tier B",
  C: "Tier C",
  skip: "Skip",
  manual: "Manual",
};

// Known documents in a job folder, in display order.
export const DOCUMENTS: { match: RegExp; title: string; open: string }[] = [
  { match: /^resume\.pdf$/, title: "Résumé", open: "View résumé" },
  { match: /^cover_letter\.(md|pdf|txt)$/, title: "Cover letter", open: "View cover letter" },
  { match: /^answers\.json$/, title: "Answers", open: "Review answers" },
  { match: /^outreach\.json$/, title: "Outreach drafts", open: "View drafts" },
];
