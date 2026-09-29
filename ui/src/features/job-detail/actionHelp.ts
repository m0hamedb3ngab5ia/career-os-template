// One-sentence help for every action button on the Job detail and Runs screens, shown as the button's `title`
// (hover tooltip; assistive tech reads it as the description). Keep each to one plain sentence.
export const ACTION_HELP = {
  rerunQa: "Re-runs the deterministic QA checks on the current documents and refreshes the QA section.",
  withdraw: "Marks this application withdrawn; it leaves the pipeline and the tracker records it.",
  markSubmitted: "Records that you submitted this application yourself and freezes a copy of the documents.",
  setStatus: "Changes where this job is in the pipeline; the tracker is updated too.",
  override: "Forces the tier (A, B, C), skips the job, or takes it out of automation with manual.",
  openFolder: "Opens this job's folder on your computer.",
  showInFolder: "Opens the folder that holds the frozen copy you submitted.",
  startPipeline: "Starts a run for this job only: score, tailor, cover letter and QA, then stops for your review.",
  continuePipeline: "Picks the pipeline up from the last completed step for this job.",
  approveContinue: "Approves the current documents and lets the pipeline continue to the next step.",
  stageReview: "Fills the form and uploads the documents in Chrome, then stops before Submit so you review and send it yourself (Tier A, and every job while auto-submit is off, is never auto-submitted).",
  cancelRun: "Stops the running batch before its next job; the job in progress finishes first.",
  pause: "Pauses all runs, scheduled and manual, until the time you choose.",
  resume: "Resumes runs; scheduled runs start again at their next slot.",
  startRun: "Starts a batch run with the type and budget chosen above; it never submits applications.",
  startStep: "Runs the selected step once (no budget); it never submits applications.",
  showSelection: "Shows which jobs the budget would pick, without running anything.",
  changeBudget: "Goes back to the budget presets so you can pick a different size.",
  skipMissed: "Dismisses the runs that were missed while your Mac was asleep or off; nothing is run.",
  catchUp: "Runs the batches that were missed while your Mac was asleep or off, one after the other.",
  installSchedule: "Installs the background schedule so runs start on their own.",
  uninstallSchedule: "Removes the background schedule; runs then start only when you start them.",
  stopAfterStage: "Stops the chained score → prepare run after scoring, instead of continuing on to prepare.",
} as const;

export type ActionKey = keyof typeof ACTION_HELP;

/** Spread onto a button: `<Button {...help("rerunQa")}>`. */
export function help(key: ActionKey): { title: string } {
  return { title: ACTION_HELP[key] };
}
