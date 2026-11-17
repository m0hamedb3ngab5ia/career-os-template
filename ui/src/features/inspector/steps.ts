// Where a job is on its way to being sent, in plain words. Pure: derived from tracker status + files present + qa.json.

export type StepState = "done" | "current" | "failed" | "todo";
export interface Step {
  label: "Scored" | "Drafted" | "Quality check" | "Ready" | "Applied";
  state: StepState;
}

export interface StepInput {
  status?: string | null;
  fit?: number | null;
  /** File names present in the job folder (documents list). */
  files: readonly string[];
  /** qa.json passed flag; null/undefined = no check yet. */
  qaPassed?: boolean | null;
}

const APPLIED = ["applied", "screening", "interview", "offer", "rejected", "withdrawn", "ghosted"];

export function deriveSteps({ status, fit, files, qaPassed }: StepInput): Step[] {
  const applied = APPLIED.includes(status ?? "");
  const drafted = files.some((f) => /^resume\./.test(f)) && files.some((f) => /^cover_letter\./.test(f));
  const checked = qaPassed === true || qaPassed === false;
  const ready = applied || status === "queued";
  const done = [fit != null || drafted || applied, drafted || applied, qaPassed === true || ready, ready, applied];
  const labels: Step["label"][] = ["Scored", "Drafted", "Quality check", "Ready", "Applied"];
  let seenCurrent = false;
  return labels.map((label, i) => {
    if (done[i]) return { label, state: "done" as const };
    if (label === "Quality check" && checked && qaPassed === false) {
      seenCurrent = true;
      return { label, state: "failed" as const };
    }
    if (!seenCurrent) {
      seenCurrent = true;
      return { label, state: "current" as const };
    }
    return { label, state: "todo" as const };
  });
}

/** "Quality check" or "Ready": the first step not finished, for list rows. */
export const currentStep = (steps: readonly Step[]): Step["label"] | null =>
  steps.find((s) => s.state !== "done")?.label ?? null;

/** Cover letters start with YAML frontmatter (job id, QA fields): readers see only the letter. */
export const withoutFrontmatter = (t: string): string => t.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n+/, "");
