import { Moon, Pause as PauseIcon, Play } from "lucide-react";
import { useId, useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { Popover } from "../../kit/Popover";
import { useToast } from "../../kit/Toast";
import { formatClock, formatCount, formatWhen } from "../../lib/format";
import { useNow } from "../../lib/useNow";
import { useCatchUp, useMeta, usePause, useResume } from "./api";
import { kindLabel } from "./labels";
import styles from "./Runs.module.css";
import type { CatchUp, Pause } from "./types";

type PauseChoice = "hour" | "tomorrow" | "resume";

const DEFAULT_TOMORROW_AT = "08:00"; // pipeline.yaml: ui.pause_until_tomorrow_at (Recommended)

/** Tomorrow at `hhmm` local time. Built from the calendar date, so a DST change overnight keeps the wall clock. */
export function tomorrowAt(now: Date, hhmm: string): Date {
  const m = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(hhmm) ?? /^(\d\d):(\d\d)$/.exec(DEFAULT_TOMORROW_AT)!;
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, Number(m[1]), Number(m[2]), 0, 0);
}

export function untilFor(choice: PauseChoice, now: Date, tomorrow: string): string | null {
  if (choice === "hour") return "+1h";
  if (choice === "tomorrow") return tomorrowAt(now, tomorrow).toISOString();
  return null;
}

/** Toolbar control: Pause all runs (1 hour, until tomorrow, until I resume) or, while paused, Resume all runs. */
export function PauseAllControl({ paused }: { paused: Pause | null | undefined }) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState<PauseChoice>("resume");
  const pause = usePause();
  const resume = useResume();
  const toast = useToast();
  const name = useId();
  const tomorrow = useMeta().data?.ui.pause_until_tomorrow_at ?? DEFAULT_TOMORROW_AT;

  if (paused) {
    return (
      <Button
        icon={<Play size={14} strokeWidth={1.7} aria-hidden="true" />}
        pending={resume.isPending}
        pendingLabel="Resuming…"
        onClick={() => resume.mutate(undefined, { onSuccess: () => toast.show({ message: "Runs resumed." }) })}
      >
        Resume all runs
      </Button>
    );
  }
  const options: { value: PauseChoice; label: string; rec?: boolean }[] = [
    { value: "hour", label: "For 1 hour" },
    { value: "tomorrow", label: `Until tomorrow, ${formatClock(tomorrow)}` },
    { value: "resume", label: "Until I resume", rec: true },
  ];
  return (
    <div className={styles.popoverAnchor}>
      <Button
        ref={anchor}
        icon={<PauseIcon size={14} strokeWidth={1.7} aria-hidden="true" />}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((o) => !o)}
      >
        Pause all runs
      </Button>
      <Popover open={open} onClose={() => setOpen(false)} anchorRef={anchor} label="Pause all runs" className={styles.pausePopover}>
        <fieldset className={styles.fieldset}>
          <legend className={styles.legend}>Pause every run</legend>
          {options.map((o) => (
            <label key={o.value} className={styles.radioRow} data-on={choice === o.value || undefined}>
              <input
                type="radio"
                name={name}
                value={o.value}
                checked={choice === o.value}
                onChange={() => setChoice(o.value)}
              />
              <span className={styles.grow}>{o.label}</span>
              {o.rec ? <Chip tone="green">Recommended</Chip> : null}
            </label>
          ))}
        </fieldset>
        <p className={styles.caption}>The running batch stops before its next job. Scheduled runs are skipped, not saved up.</p>
        <Button
          variant="primary"
          pending={pause.isPending}
          pendingLabel="Pausing…"
          onClick={() =>
            pause.mutate(untilFor(choice, new Date(), tomorrow), {
              onSuccess: () => {
                setOpen(false);
                anchor.current?.focus();
                toast.show({ message: "All runs paused." });
              },
            })
          }
        >
          Pause all runs
        </Button>
        {pause.error ? (
          <p role="alert" className={styles.fix}>
            {pause.error.message}
          </p>
        ) : null}
      </Popover>
    </div>
  );
}

export function PausedBanner({ paused }: { paused: Pause }) {
  const resume = useResume();
  const now = useNow(60_000);
  const until = paused.until ? `until ${formatWhen(paused.until, now)}` : "until you resume";
  return (
    <div role="status" className={styles.banner} data-kind="gray">
      <PauseIcon size={16} strokeWidth={1.7} aria-hidden="true" />
      <div className={styles.grow}>
        <div className={styles.strong}>All runs paused {until}</div>
        <div className={styles.caption}>
          Scheduled runs are skipped until you resume. The current batch stops at the next safe point.
        </div>
      </div>
      <Button variant="primary" size="small" pending={resume.isPending} pendingLabel="Resuming…" onClick={() => resume.mutate()}>
        Resume
      </Button>
    </div>
  );
}

export function catchUpText(rec: CatchUp, now: Date): { title: string; detail: string } {
  const kinds = Object.entries(rec.kinds);
  const slots = kinds.reduce((n, [, v]) => n + (v.slots || 1), 0);
  const title = `Missed ${formatCount(slots)} ${slots === 1 ? "run" : "runs"} while your Mac was off`;
  const detail = kinds
    .map(([k, v]) => {
      const since = formatWhen(v.first_missed, now);
      const n = v.slots || 1;
      return `${kindLabel(k)}: ${formatCount(n)} ${n === 1 ? "slot" : "slots"}${since ? ` since ${since}` : ""}`;
    })
    .join(" · ");
  return { title, detail: `${detail} · run once now as one catch-up run` };
}

/** Missed scheduled slots: Catch up now (one catch-up run) or Skip missed runs (they run at their next time). */
export function CatchUpBanner({ record }: { record: CatchUp }) {
  const catchUp = useCatchUp();
  const toast = useToast();
  const now = useNow(60_000);
  const [asking, setAsking] = useState(false);
  const skipButton = useRef<HTMLButtonElement>(null);
  const { title, detail } = catchUpText(record, now);
  return (
    <div role="region" aria-label="Missed runs" className={styles.banner} data-kind="orange">
      <span className={styles.bannerIcon}>
        <Moon size={18} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <div className={styles.grow}>
        <div className={styles.strong}>{title}</div>
        <div className={styles.caption}>{detail}</div>
        {asking ? (
          <div className={styles.block}>
            <ConfirmPanel
              question="Skip the missed runs? They run at their next scheduled time."
              cancelLabel="Keep them"
              confirmLabel="Skip missed runs"
              pending={catchUp.isPending}
              returnFocusRef={skipButton}
              onCancel={() => setAsking(false)}
              onConfirm={() =>
                catchUp.mutate(true, {
                  onSuccess: () => toast.show({ message: "Missed runs skipped. They run at their next scheduled time." }),
                  onSettled: () => setAsking(false),
                })
              }
            />
          </div>
        ) : null}
        {catchUp.error ? (
          <p role="alert" className={styles.fix}>
            {catchUp.error.message}
          </p>
        ) : null}
      </div>
      {asking ? null : (
        <>
          <Button ref={skipButton} size="small" onClick={() => setAsking(true)}>
            Skip missed runs
          </Button>
          <Button
            size="small"
            variant="primary"
            icon={<Play size={14} strokeWidth={1.7} aria-hidden="true" />}
            pending={catchUp.isPending}
            pendingLabel="Starting…"
            onClick={() =>
              catchUp.mutate(false, { onSuccess: () => toast.show({ message: "Catch-up run started." }) })
            }
          >
            Catch up now
          </Button>
        </>
      )}
    </div>
  );
}
