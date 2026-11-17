import type { ActionItem, OutreachItem } from "./types";

// Today's "needs you" list, grouped by what the person does next, in plain words.
// Pure: the screen and tests share it. Raw action text is machine-written; nothing here shows it as-is.

export type SectionKey = "eligibility" | "send" | "reach" | "followup" | "answers" | "resume" | "safety" | "stale" | "failed" | "other";

export interface Row {
  id: string;
  /** Every action this row stands for (duplicates of one job collapse into one row). */
  items: ActionItem[];
  title: string;
  /** Role line under the title; empty for company-wide rows. */
  sub: string;
  why: string;
  cta: string;
  href: string | null;
  /** href is a posting URL: open in a new tab. Otherwise it is `?job=<id>`, which opens the job inspector. */
  external?: boolean;
  /** The system notices when it is done (finishing the workflow closes it): no "Done" button. */
  detected: boolean;
  /** Question/salary rows carry an inline Answer control instead of a link. */
  answerable?: boolean;
}

export interface Section {
  key: SectionKey;
  title: string;
  caption: string;
  rows: Row[];
}

const ORDER: { key: SectionKey; title: string; caption: string }[] = [
  { key: "send", title: "Ready to send", caption: "Prepared and waiting for your approval." },
  { key: "reach", title: "Reach out", caption: "Drafts are written. You send them yourself." },
  { key: "followup", title: "Follow up", caption: "No answer yet. A short nudge often gets one." },
  { key: "answers", title: "Questions only you can answer", caption: "The form can’t be finished without you." },
  { key: "eligibility", title: "Check you’re eligible", caption: "These ask for a graduation date that differs from yours." },
  { key: "resume", title: "Résumé fell short", caption: "Didn’t pass the quality check. Apply anyway, or skip." },
  { key: "safety", title: "Look before applying", caption: "Something in the posting looks wrong." },
  { key: "stale", title: "May no longer be hiring", caption: "Postings that haven’t changed in months." },
  { key: "failed", title: "Couldn’t finish", caption: "Automation stopped partway." },
  { key: "other", title: "Everything else", caption: "" },
];

const MONTH = "(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\\.?";
const DATE = `(?:${MONTH}\\s*\\d{4}|\\d{4}-\\d{2})`;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-05" → "May 2026"; "December 2026" → "Dec 2026". */
const date = (s: string | undefined = "") => {
  const iso = /^(\d{4})-(\d{2})$/.exec(s.trim());
  if (iso) return `${MONTHS[Number(iso[2]) - 1] ?? ""} ${iso[1] ?? ""}`;
  return s.trim().replace(/^(\w{3})\w*\.?\s*/, "$1 ");
};

const isEligibility = (t: string) => /graduat|eligib/i.test(t);

function sectionOf(a: ActionItem): SectionKey {
  const t = a.what ?? "";
  if (/chrome/i.test(t)) return "other";
  if (a.type === "review" || a.type === "question" || a.type === "salary") {
    if (isEligibility(t)) return "eligibility";
    if (a.type === "review") return "send";
    return "answers";
  }
  if (a.type === "follow_up") return "followup";
  if (a.type === "qa_fail") return "resume";
  if (a.type === "scam_suspected" || a.type === "injection_suspected") return "safety";
  if (a.type === "ghost_job") return "stale";
  if (/couldn.t|failed/i.test(t)) return "failed";
  return "other";
}

/** "Wants a Dec 2026–Jun 2027 graduate. You graduated May 2026." */
function eligibilityWhy(t: string): string {
  const range = new RegExp(`(${DATE})\\s*(?:-|–|and|to)\\s*(${DATE})`, "i").exec(t);
  const one = new RegExp(`graduating\\s+(${DATE})`, "i").exec(t);
  const mine = new RegExp(`graduat\\w*\\s+(?:in\\s+)?(${DATE})\\W*(?:\\.|$|;|\\s*Confirm)`, "i").exec(t.replace(range?.[0] ?? "\u0000", ""));
  const want = range ? `${date(range[1])}–${date(range[2])}` : one ? date(one[1]) : null;
  const you = mine ? ` You graduated ${date(mine[1])}.` : "";
  return want ? `Wants a ${want} graduate.${you}` : "Asks for a different graduation date than yours.";
}

/** "Covers 38% of the posting’s keywords. Nothing shows Go, GCP or blockchain." */
function resumeWhy(t: string): string {
  const cov = /keyword coverage ([\d.]+)/.exec(t);
  const gap = /\bno ([^;)]+?) evidence/.exec(t);
  const parts = [
    cov ? `Covers ${Math.round(Number(cov[1]) * 100)}% of the posting’s keywords.` : null,
    gap?.[1] ? `Your profile doesn’t show ${orList(gap[1])}.` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : "Didn’t pass the quality check.";
}

/** "Go, GCP or blockchain/stablecoin" → "Go, GCP, blockchain or stablecoin". */
function orList(t: string): string {
  const xs = t.split(/\s*(?:,|\/|\bor\b|\band\b)\s*/).filter(Boolean);
  return xs.length < 2 ? t : `${xs.slice(0, -1).join(", ")} or ${xs.at(-1)}`;
}

function staleWhy(a: ActionItem): string {
  const n = /(\d+) jobs?/.exec(a.what ?? "")?.[1];
  const days = [...(a.detail ?? "").matchAll(/posted (\d+) days ago/g)].map((m) => Number(m[1]));
  const oldest = days.length ? Math.max(...days) : 0;
  const age = oldest >= 365 ? `${Math.floor(oldest / 365)}+ years` : oldest >= 60 ? `${Math.floor(oldest / 30)} months` : "";
  const count = n ? `${n} ${n === "1" ? "posting" : "postings"}` : "Postings";
  return age ? `${count}, oldest up for ${age}.` : `${count} not updated in a while.`;
}

/** Title for a job-less eligibility/question item: "Acme SWE New Grad (0a1b…): …" → "Acme SWE New Grad". */
const nameFromText = (t: string) => /^([^(:]{3,60}?)\s*\(\w{6,}\)/.exec(t)?.[1]?.trim() ?? "";

/** Safety and stale rows send you to the posting itself, not the inspector. */
const ext = (url: string | null): Pick<Row, "href" | "external"> => ({ href: url, external: !!url });

export function toRow(a: ActionItem, key: SectionKey): Row {
  const t = a.what ?? "";
  const job = a.job_id ? `?job=${encodeURIComponent(a.job_id)}` : null;
  const posting = /^https?:\/\//i.test(a.link ?? "") ? a.link : null;
  const title = a.company || nameFromText(t) || "A job";
  const sub = a.company ? a.role ?? "" : "";
  const base: Row = { id: String(a.id), items: [a], title, sub, href: job, why: "", cta: "", detected: false };
  switch (key) {
    case "eligibility":
      return { ...base, why: eligibilityWhy(t), cta: "Review", detected: true };
    case "followup":
      return { ...base, sub: a.role ?? "", why: t, cta: "Open", detected: false };
    case "send":
      return { ...base, why: "Check the résumé and cover letter, then send.", cta: "Review", detected: true };
    case "answers":
      return { ...base, href: null, why: answerWhy(t), cta: "Answer", detected: true, answerable: true };
    case "resume":
      return { ...base, why: resumeWhy(t), cta: "Review", detected: true };
    case "safety":
      return a.type === "scam_suspected"
        ? { ...base, ...ext(posting), why: "Asks applicants for money. Blocked.", cta: "Read posting" }
        : { ...base, ...ext(posting), why: "Has text hidden from readers. Read it before applying.", cta: "Read posting" };
    case "stale":
      return { ...base, ...ext(posting), title: a.company || "A company", sub: "", why: staleWhy(a), cta: posting ? "Read posting" : "", detected: false };
    case "failed":
      return { ...base, why: "Scoring stopped partway. Try again, or score it yourself.", cta: "Open", detected: false };
    default: {
      const cat = /new_category_review:\s*(\w+)/.exec(t)?.[1];
      if (cat) {
        const name = cat.replace(/_/g, " ").replace(/\bml\b/, "ML").replace(/\bswe\b/, "SWE");
        return { ...base, why: `A new kind of role for you: ${name}. Want more like it?`, cta: "Review", detected: false };
      }
    }
      if (/chrome/i.test(t)) return { ...base, title: "Connect Chrome", sub: "", why: "Needed to fill applications in your browser.", cta: "", href: null, detected: false };
      return { ...base, why: firstSentence(t), cta: job ? "Open" : "", detected: false };
  }
}

/** The question itself, plainly. A fill plan has no question text of its own. */
function answerWhy(t: string): string {
  if (/^\s*fill plan\b/i.test(t)) return "The form has questions only you can answer.";
  return firstSentence(t) || "The form has questions only you can answer.";
}

/** First sentence of machine text, minus commands, paths, ids and "label:" prefixes. */
function firstSentence(t: string): string {
  const s = t
    .replace(/`[^`]*`/g, "")
    .replace(/\S*\/\S*|\S+\.(ya?ml|json)\b/g, "")
    .replace(/\(\s*\w{8,}\s*\)/g, "")
    .replace(/^[a-z_]+:\s*/i, "")
    .split(/(?<=[.!?])\s|;\s/)[0]!
    .replace(/\s{2,}/g, " ")
    .trim()
    .replace(/[.:,]$/, "");
  return s ? `${s.charAt(0).toUpperCase()}${s.slice(1)}${/[?!]$/.test(s) ? "" : "."}` : "";
}

const ROLE: Record<string, string> = { recruiter: "Recruiter", hiring_manager: "Hiring manager", team_lead: "Team lead" };

/** "Recruiter Jane Doe · email likely jane@acme.com · draft ready · follow up by Oct 3". Plain words, no raw codes. */
export function outreachWhy(o: OutreachItem): string {
  const who = o.contact_name ? `${ROLE[o.contact_role ?? ""] ?? "Contact"} ${o.contact_name}` : null;
  const email = !o.email ? null
    : o.email_confidence === "verified" ? `email ${o.email}`
    : o.email_confidence === "medium" ? `email likely ${o.email}`
    : "email unconfirmed";
  const due = o.followup_due ? new Date(`${o.followup_due.slice(0, 10)}T12:00:00`) : null;
  const followUp = due && !Number.isNaN(due.getTime()) ? `follow up by ${MONTHS[due.getMonth()]} ${due.getDate()}` : null;
  return [who, email, o.draft_ready ? "draft ready" : "no draft yet", followUp].filter(Boolean).join(" · ");
}

function outreachRow(o: OutreachItem): Row {
  return { id: `reach:${o.job_id}`, items: [], title: o.company || "A company", sub: o.title,
    why: outreachWhy(o), cta: "Open", href: `?job=${encodeURIComponent(o.job_id)}`, detected: true };
}

/** Group open actions into sections; one row per job per section (duplicates merge). Empty sections dropped.
 *  `outreach` (GET /api/today) fills the "Reach out" section. */
export function buildSections(actions: readonly ActionItem[], outreach: readonly OutreachItem[] = []): Section[] {
  const rows = new Map<SectionKey, Map<string, Row>>();
  if (outreach.length) rows.set("reach", new Map(outreach.map((o) => [`job:${o.job_id}`, outreachRow(o)])));
  for (const a of actions) {
    if (a.done) continue;
    const key = sectionOf(a);
    const bucket = rows.get(key) ?? new Map<string, Row>();
    rows.set(key, bucket);
    const dedupe = key === "stale" ? `co:${a.company}` : a.job_id ? `job:${a.job_id}` : `text:${a.what}`;
    const prev = bucket.get(dedupe);
    if (prev) prev.items.push(a);
    else bucket.set(dedupe, toRow(a, key));
  }
  return ORDER.flatMap((s) => {
    const r = [...(rows.get(s.key)?.values() ?? [])];
    return r.length ? [{ ...s, rows: r }] : [];
  });
}

/** One calm sentence for the top of the page. */
export function summary(sections: readonly Section[]): string {
  const n = sections.reduce((t, s) => t + s.rows.length, 0);
  const first = sections[0];
  if (!n || !first) return "You’re all caught up.";
  const lead: Record<SectionKey, string> = {
    send: `${count(first.rows.length, "application is", "applications are")} ready to send.`,
    reach: `${count(first.rows.length, "contact is", "contacts are")} ready to reach out to.`,
    followup: `${count(first.rows.length, "application has", "applications have")} had no reply yet.`,
    answers: `${count(first.rows.length, "form needs", "forms need")} your answers.`,
    eligibility: `Start by confirming you’re eligible for ${count(first.rows.length, "job", "jobs")}.`,
    resume: `${count(first.rows.length, "résumé needs", "résumés need")} a decision.`,
    safety: `${count(first.rows.length, "posting looks", "postings look")} suspicious.`,
    stale: `${count(first.rows.length, "company may", "companies may")} have stopped hiring.`,
    failed: `${count(first.rows.length, "job", "jobs")} couldn’t be finished.`,
    other: `${count(first.rows.length, "thing needs", "things need")} a look.`,
  };
  return n === first.rows.length ? lead[first.key] : `${lead[first.key]} ${count(n - first.rows.length, "other thing needs", "other things need")} a look.`;
}

const count = (n: number, one: string, many: string) => `${n === 1 ? "One" : n} ${n === 1 ? one : many}`;
