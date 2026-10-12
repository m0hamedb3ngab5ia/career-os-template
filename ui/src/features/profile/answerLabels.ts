import type { SavedAnswer } from "./api";

export const GROUPS = ["Work & eligibility", "Job preferences", "Education", "Experience", "Links", "Personal information", "EEO (voluntary)", "Company-specific", "Other"] as const;
export type Group = (typeof GROUPS)[number];

const KNOWN: Record<string, [string, Group]> = {
  work_authorization: ["Authorized to work", "Work & eligibility"],
  sponsorship: ["Needs visa sponsorship", "Work & eligibility"],
  citizenship: ["Citizenship status", "Work & eligibility"],
  over_18: ["At least 18 years old", "Work & eligibility"],
  non_compete: ["Non-compete agreement", "Work & eligibility"],
  security_clearance: ["Security clearance", "Work & eligibility"],
  relocate: ["Willing to relocate", "Job preferences"],
  remote_hybrid: ["Fine with on-site or hybrid", "Job preferences"],
  start_date: ["Start date", "Job preferences"],
  salary_expectation: ["Salary expectation", "Job preferences"],
  previously_applied: ["Previously applied", "Job preferences"],
  referral: ["Referral", "Job preferences"],
  degree: ["Highest degree", "Education"],
  school: ["School", "Education"],
  major: ["Major", "Education"],
  grad_year: ["Graduation year", "Education"],
  gpa: ["GPA", "Education"],
  current_employer: ["Current employer", "Experience"],
  current_title: ["Current title", "Experience"],
  years_experience_fulltime: ["Years of full-time experience", "Experience"],
  years_experience: ["Years of experience", "Experience"],
  linkedin: ["LinkedIn", "Links"],
  github: ["GitHub", "Links"],
  pronouns: ["Pronouns", "Personal information"],
  phone: ["Phone", "Personal information"],
  address: ["Address", "Personal information"],
};

const humanize = (k: string) => { const s = k.replace(/_/g, " "); return s.charAt(0).toUpperCase() + s.slice(1); };

/** Plain-language label + group for a saved answer. EEO and per-company scopes override the key. */
export function describeAnswer(a: Pick<SavedAnswer, "key" | "scope" | "company">): { label: string; group: Group } {
  const [label, group] = KNOWN[a.key] ?? [humanize(a.key), "Other" as Group];
  if (a.scope === "eeo") return { label: humanize(a.key), group: "EEO (voluntary)" };
  if (a.scope === "company") return { label: `${label}${a.company ? ` (${a.company})` : ""}`, group: "Company-specific" };
  return { label, group };
}

/** Answers bucketed by group, in GROUPS order, empty groups dropped. */
export function groupAnswers(answers: SavedAnswer[]): { group: Group; rows: SavedAnswer[] }[] {
  return GROUPS.map((group) => ({ group, rows: answers.filter((a) => describeAnswer(a).group === group) })).filter((g) => g.rows.length);
}
