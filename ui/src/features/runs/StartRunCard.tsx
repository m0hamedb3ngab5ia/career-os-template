import { Play } from "lucide-react";
import { useId, useState } from "react";
import { useSearchParams } from "react-router";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { humanize } from "../../kit/labels";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { help } from "../job-detail/actionHelp";
import { Switch } from "../../kit/Switch";
import { useToast } from "../../kit/Toast";
import { formatNumber } from "../../lib/format";
import { useStartRun, useStartStep, type StartVars } from "./api";
import { START_KINDS, isStartKind, type StartKind } from "./labels";
import { ReasonChips } from "./ReasonChips";
import styles from "./Runs.module.css";
import type { Meta, Schedule, Selection } from "./types";

const STEP_OF: Record<string, "scout" | "tracker" | "inbox_sync"> = {
  scout: "scout",
  tracker: "tracker",
  inbox: "inbox_sync",
};

/** The mockup's budget wording: "30 min", "90 min", "3 h", "8 h". */
export function budgetMinutes(m: number): string {
  return m >= 120 && m % 60 === 0 ? `${formatNumber(m / 60)} h` : `${formatNumber(m)} min`;
}

function presetDetail(meta: Meta, name: string): string {
  if (name === "custom") return "set your own limits";
  const v = meta.presets.values[name];
  if (!v) return "";
  return `score ${formatNumber(v.max_score_jobs)} · prepare ${formatNumber(v.max_prepare_jobs)} · ${budgetMinutes(v.max_minutes)}`;
}

interface StartRunCardProps {
  meta: Meta | undefined;
  schedule: Schedule | undefined;
  paused: boolean;
}

/** Start a run: kind, budget (score and prepare), "Dry run first" showing the selection before anything runs. */
export function StartRunCard({ meta, schedule, paused }: StartRunCardProps) {
  const [params, setParams] = useSearchParams();
  const toast = useToast();
  const start = useStartRun();
  const step = useStartStep();
  const ids = { jobs: useId(), minutes: useId(), error: useId() };
  const rawKind = params.get("kind");
  const kind: StartKind = isStartKind(rawKind) ? rawKind : "prepare";
  const batch = kind === "score" || kind === "prepare";
  const preset = params.get("budget") ?? meta?.presets.current ?? "medium";
  const [dryFirst, setDryFirst] = useState(true);
  const custom = meta?.presets.values.custom;
  const [jobs, setJobs] = useState<string>("");
  const [minutes, setMinutes] = useState<string>("");
  const [selection, setSelection] = useState<Selection | null>(null);
  const info = START_KINDS.find((k) => k.value === kind)!;
  const inboxOff = kind === "inbox" && !schedule?.inbox_ready;

  const [invalid, setInvalid] = useState<string | null>(null);

  /** Any change to what would run drops the dry-run selection and the last answer. */
  function forget() {
    setSelection(null);
    setInvalid(null);
    start.reset();
    step.reset();
  }

  function set(key: string, value: string) {
    forget();
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  }

  function vars(dry: boolean): StartVars {
    const k = kind as "score" | "prepare";
    if (preset !== "custom") return { kind: k, preset, dry_run: dry };
    const defJobs = k === "score" ? custom?.max_score_jobs : custom?.max_prepare_jobs;
    return {
      kind: k,
      preset: "custom",
      max_jobs: jobs ? Number(jobs) : defJobs,
      max_minutes: minutes ? Number(minutes) : custom?.max_minutes,
      dry_run: dry,
    };
  }

  const label = `Start ${info.label.toLowerCase()} run`;
  const started = (what: string) => toast.show({ message: `${what} run started.` });

  function customProblem(): string | null {
    if (preset !== "custom") return null;
    if (jobs && !(Number.isInteger(Number(jobs)) && Number(jobs) >= 1)) return "Jobs must be a whole number, 1 or more.";
    if (minutes && !(Number(minutes) > 0)) return "Minutes must be more than 0.";
    return null;
  }

  function onStart() {
    if (batch) {
      const problem = customProblem();
      setInvalid(problem);
      if (problem) return;
    }
    if (!batch) {
      step.mutate(STEP_OF[kind]!, { onSuccess: () => started(info.label) });
      return;
    }
    if (dryFirst && !selection) {
      start.mutate(vars(true), { onSuccess: (out) => setSelection(out as Selection) });
      return;
    }
    start.mutate(vars(false), {
      onSuccess: () => {
        setSelection(null);
        started(info.label);
      },
    });
  }

  const error = start.error ?? step.error;
  const pending = start.isPending || step.isPending;
  const disabledReason = inboxOff
    ? "Inbox sync isn't set up yet: turn it on in Settings › Runs once the inbox-sync skill is ready and Gmail is logged in."
    : paused && kind !== "scout" && kind !== "tracker"
      ? "Runs are paused. Resume them to start one."
      : null;

  return (
    <section className={styles.card} aria-labelledby="start-h">
      <h2 id="start-h" className={styles.h2}>
        Start a run
      </h2>
      <div className={styles.block}>
        <SegmentedControl label="Run type" value={kind} onValueChange={(v) => set("kind", v)}>
          {START_KINDS.map((k) => (
            <SegmentedControl.Option key={k.value} value={k.value}>
              {k.label}
            </SegmentedControl.Option>
          ))}
        </SegmentedControl>
      </div>
      <p className={styles.sub}>{info.note}</p>

      {batch && meta ? (
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>Budget</legend>
          {meta.presets.names.map((name) => (
            <label key={name} className={styles.radioRow} data-on={preset === name || undefined}>
              <input
                type="radio"
                name="budget"
                value={name}
                checked={preset === name}
                onChange={() => set("budget", name)}
              />
              <span className={styles.grow}>
                <span className={styles.strong}>{humanize(name)}</span>{" "}
                <span className={styles.caption}>{presetDetail(meta, name)}</span>
              </span>
              {name === meta.presets.recommended ? <Chip tone="green">Recommended</Chip> : null}
            </label>
          ))}
          {preset === "custom" ? (
            <div className={styles.customRow}>
              <label htmlFor={ids.jobs} className={styles.field}>
                <span className={styles.caption}>Jobs</span>
                <input
                  id={ids.jobs}
                  name="max_jobs"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  autoComplete="off"
                  className={styles.input}
                  placeholder={String(
                    (kind === "score" ? custom?.max_score_jobs : custom?.max_prepare_jobs) ?? "",
                  )}
                  value={jobs}
                  step={1}
                  aria-invalid={invalid?.startsWith("Jobs") || undefined}
                  onChange={(e) => {
                    forget();
                    setJobs(e.target.value);
                  }}
                />
              </label>
              <label htmlFor={ids.minutes} className={styles.field}>
                <span className={styles.caption}>Minutes</span>
                <input
                  id={ids.minutes}
                  name="max_minutes"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  autoComplete="off"
                  className={styles.input}
                  placeholder={String(custom?.max_minutes ?? "")}
                  value={minutes}
                  aria-invalid={invalid?.startsWith("Minutes") || undefined}
                  onChange={(e) => {
                    forget();
                    setMinutes(e.target.value);
                  }}
                />
              </label>
            </div>
          ) : null}
          {invalid ? (
            <p role="alert" className={styles.fix}>
              {invalid}
            </p>
          ) : null}
          <div className={styles.switchLine}>
            <Switch
              checked={dryFirst}
              onCheckedChange={(v) => {
                setDryFirst(v);
                setSelection(null);
              }}
              label="Dry run first"
            />
            <Chip tone="green">Recommended</Chip>
          </div>
        </fieldset>
      ) : null}

      {selection ? (
        <div className={styles.selection} aria-label="Dry run selection" role="region">
          <div className={styles.strong}>
            {selection.selected.length
              ? `${formatNumber(selection.selected.length)} of ${formatNumber(selection.candidates)} jobs would run`
              : "Nothing to run: the queue is empty"}
          </div>
          <ol className={styles.selectionList}>
            {selection.selected.map((j) => (
              <li key={j.job_id}>
                <span className={styles.strong}>{j.company}</span> <span className={styles.sec}>{j.title}</span>
                <ReasonChips reasons={j.reasons} />
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <Button
        variant="primary"
        {...help(!batch ? "startStep" : dryFirst && !selection ? "showSelection" : "startRun")}
        className={styles.startButton}
        icon={<Play size={14} strokeWidth={1.7} aria-hidden="true" />}
        onClick={onStart}
        pending={pending}
        pendingLabel="Starting…"
        disabled={Boolean(disabledReason) || (selection !== null && selection.selected.length === 0)}
        aria-describedby={disabledReason || error ? ids.error : undefined}
      >
        {batch && dryFirst && !selection ? "Show the selection" : label}
      </Button>
      {selection ? (
        <Button size="small" {...help("changeBudget")} className={styles.startButton} onClick={() => setSelection(null)}>
          Change the budget
        </Button>
      ) : null}
      {disabledReason || error ? (
        <p id={ids.error} role={error ? "alert" : undefined} className={styles.fix}>
          {error ? error.message : disabledReason}
        </p>
      ) : null}
      <p className={styles.caption}>Never applies: apply stays manual in this version.</p>
    </section>
  );
}
