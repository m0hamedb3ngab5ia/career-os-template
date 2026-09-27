import type { FieldSchema } from "./types";

// Plain-language labels for option codes and values shown in Settings. Unknown codes are humanized.

export function humanize(code: string): string {
  const s = code.replace(/_/g, " ").trim();
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

const OPTION_LABELS: Record<string, string> = {
  always: "Always",
  if_required: "If required",
  if_contact_found: "If contact found",
  never: "Never",
  push: "Push",
  none: "None",
  action_item_only: "Action Item only",
  new_grad: "New grad",
  early_career: "Early career",
  us_citizen: "US citizen",
  permanent_resident: "Permanent resident",
  visa: "Visa",
  system: "Match the system",
  light: "Light",
  dark: "Dark",
  tectonic: "Tectonic",
  pdflatex: "pdfLaTeX",
  resume: "Résumé",
  cover_letter: "Cover letter",
  answers: "Answers",
  form: "Form",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workday: "Workday",
  icims: "iCIMS",
  taleo: "Taleo",
  smartrecruiters: "SmartRecruiters",
  jobvite: "Jobvite",
  successfactors: "SuccessFactors",
  custom: "Custom",
  small: "Small",
  medium: "Medium",
  large: "Large",
  max: "Max",
  captcha: "Captcha",
  account_creation_email_verify: "Account needs email verification",
  question_not_in_standard_answers: "Question not in your standard answers",
  salary_field_freeform: "Free-text salary field",
  bot_detection_suspected: "Bot detection suspected",
  file_upload_failed: "File upload failed",
  qa_failed_twice: "QA failed twice",
};

export function optionLabel(v: unknown): string {
  const s = String(v);
  return OPTION_LABELS[s] ?? humanize(s);
}

/** Plain-language names for safety check codes (src/careeros/safety/scam.py, ghost.py). */
export const REASON_CODES: Record<string, string> = {
  SCAM_PAYMENT_REQUEST: "Posting asks you to pay",
  SCAM_REMOTE_ACCESS_REQUEST: "Asks for remote access to your computer",
  SCAM_BRAND_DOMAIN_MISMATCH: "Big-brand name on an unrelated domain",
  SCAM_APPLY_DOMAIN_UNRECOGNIZED: "Apply page on an unrecognized domain",
  SCAM_FREE_EMAIL_RECRUITER: "Recruiter uses a free email address",
  SCAM_CHAT_ONLY_INTERVIEW: "Interview by chat only",
  SCAM_NO_INTERVIEW: "Offer without an interview",
  SCAM_SALARY_IMPLAUSIBLE: "Salary far above the norm",
  SCAM_FLAGGED_BEFORE: "Company flagged before",
  FIELD_PAYMENT: "Form asks for payment details",
  FIELD_CREDENTIALS: "Form asks for passwords or logins",
  FIELD_REMOTE_ACCESS: "Form asks for remote access",
  FIELD_SENSITIVE_PRE_OFFER: "Sensitive details before an offer",
  COMPANY_NOT_YET_CHECKED: "Company not verified yet",
  COMPANY_SPARSE_PUBLIC_FOOTPRINT: "Company has little public presence",
  COMPANY_CONTRADICTIONS: "Company details contradict each other",
  GHOST_OLD_POST: "Posting is old",
  GHOST_STALE_NO_ACTIVITY: "Old, not updated, company quiet",
  GHOST_REPOSTED: "Reposted again and again",
  GHOST_HIRING_FREEZE: "Hiring freeze reported",
  GHOST_RECENT_LAYOFFS: "Recent layoffs",
  GHOST_AGGREGATOR_ONLY: "Only on job aggregators",
};

export function reasonLabel(code: string): string {
  return REASON_CODES[code] ?? humanize(code.toLowerCase());
}

export function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a === "number" && typeof b === "number") return Number.isNaN(a) && Number.isNaN(b);
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => equal(x, b[i]));
  const ka = Object.keys(a as object);
  const kb = Object.keys(b as object);
  return (
    ka.length === kb.length &&
    ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && equal((a as never)[k], (b as never)[k]))
  );
}

const nf = new Map<string, Intl.NumberFormat>();
export function formatNumber(n: number, opts: Intl.NumberFormatOptions = {}, locale?: string): string {
  const k = `${locale ?? ""}|${JSON.stringify(opts)}`;
  let f = nf.get(k);
  if (!f) nf.set(k, (f = new Intl.NumberFormat(locale, opts)));
  return f.format(n);
}

/** A default or value as a short phrase: "On", "30 days", "Medium", "09:00–18:00". Null for shapes too big. */
export function formatValue(field: FieldSchema, v: unknown): string | null {
  if (v === null || v === undefined) return field.nullable ? "Off" : null;
  switch (field.control) {
    case "switch":
      return v ? "On" : "Off";
    case "number":
    case "slider":
      return typeof v === "number" ? `${formatNumber(v)}${field.unit ? ` ${field.unit}` : ""}` : null;
    case "select":
    case "preset_cards":
      return optionLabel(v);
    case "text":
    case "time":
      return String(v) || null;
    case "time_range": {
      const r = v as { start?: string; end?: string };
      return r.start && r.end ? `${r.start}–${r.end}` : null;
    }
    case "tags":
      return Array.isArray(v) && v.length <= 3 ? (v.length ? v.map(optionLabel).join(", ") : "None") : null;
    default:
      return null;
  }
}

/** "config/targets.yaml and config/pipeline.yaml" */
export function joinFiles(paths: string[]): string {
  if (paths.length <= 1) return paths[0] ?? "";
  return `${paths.slice(0, -1).join(", ")} and ${paths.at(-1)}`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatNumber(n)} ${n === 1 ? one : many}`;
}

const UNITS = ["byte", "kilobyte", "megabyte", "gigabyte", "terabyte"] as const;
/** Bytes as "34 MB" / "1.5 GB" (binary steps, Intl unit names). */
export function formatBytes(n: number, locale?: string): string {
  let v = Math.max(0, n);
  let i = 0;
  while (v >= 1024 && i < UNITS.length - 1) {
    v /= 1024;
    i += 1;
  }
  return formatNumber(v, { style: "unit", unit: UNITS[i], unitDisplay: "short", maximumFractionDigits: v < 10 && i > 0 ? 1 : 0 }, locale);
}

export function formatPercent(share: number, locale?: string): string {
  return formatNumber(share, { style: "percent", maximumFractionDigits: 0 }, locale);
}

export function formatDuration(seconds: number, locale?: string): string {
  if (seconds < 60) return formatNumber(Math.round(seconds), { style: "unit", unit: "second", unitDisplay: "short" }, locale);
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  const mm = formatNumber(m, { style: "unit", unit: "minute", unitDisplay: "short" }, locale);
  return s ? `${mm} ${formatNumber(s, { style: "unit", unit: "second", unitDisplay: "short" }, locale)}` : mm;
}

/** A DOM-safe id for a field id like "targets:safety.ghost.old_post_days". */
export function domId(prefix: string, fieldId: string): string {
  return `${prefix}-${fieldId.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}
