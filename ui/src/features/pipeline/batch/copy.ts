import type { JobsView } from "../../jobs/urlState";
import type { StopAt } from "./api";

export const STOP_POINTS: { value: StopAt; label: string }[] = [
  { value: "score", label: "Score only" },
  { value: "prepare", label: "Prepare documents" },
  { value: "fill", label: "Fill application, then ask me" },
  { value: "submit", label: "Submit when allowed" },
];

/** docs/design/ui-redesign.md §4.1: enforced in the backend, stated here so nobody expects otherwise. */
export const HARD_RULES = [
  "Top choice jobs are filled and staged for you, never submitted.",
  "A job whose documents fail quality checks stops at Needs your review.",
  "LinkedIn applications are never automated: they're listed for you to apply yourself.",
  "Jobs run one at a time, one application per run.",
  "Submitting only happens where your Settings already allow it; a batch can never widen that.",
  "Filling and submitting need Chrome and your sign-ins, so you start these batches; they're never scheduled.",
];

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "fit ≥ 75, found since 2026-09-21, status: scored, queued" — the filters that picked the jobs. */
export function filterSummary(view: Pick<JobsView, "q" | "location" | "filters">): string {
  const out: string[] = [];
  if (view.q) out.push(`matching "${view.q}"`);
  if (view.location) out.push(`location has "${view.location}"`);
  for (const [field, f] of Object.entries(view.filters)) {
    if (!f) continue;
    const name = field === "found_at" ? "found" : field.replace(/_at$/, "").replace(/_/g, " ");
    if (f.kind === "values") out.push(`${name}: ${f.values.join(", ")}`);
    else if (field.endsWith("_at")) {
      if (f.min) out.push(`${name} since ${f.min}`);
      if (f.max) out.push(`${name} until ${f.max}`);
    } else {
      if (f.min) out.push(`${name} ≥ ${f.min}`);
      if (f.max) out.push(`${name} ≤ ${f.max}`);
    }
  }
  return out.join(", ");
}

/** The confirm step's one sentence: "Fill 23 applications, then ask you · auto-submit off · Top choice staged · …". */
export function confirmSentence(n: number, stop: StopAt, source: string): string {
  const what = {
    score: `Score ${plural(n, "job")}`,
    prepare: `Prepare documents for ${plural(n, "job")}`,
    fill: `Fill ${plural(n, "application")}, then ask you`,
    submit: `Fill ${plural(n, "application")} and submit where your Settings allow`,
  }[stop];
  const parts = [what];
  if (stop === "fill" || stop === "submit") {
    parts.push(stop === "submit" ? "auto-submit on, within your rules and daily cap" : "auto-submit off", "Top choice staged");
  }
  if (source) parts.push(source);
  return parts.join(" · ");
}
