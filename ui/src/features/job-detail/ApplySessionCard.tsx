import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { Dialog } from "../../kit/Dialog";
import { describeCode, type CodeTable } from "../../kit/labels";
import { formatDateTime } from "../../lib/format";
import { fileUrl } from "./api";
import { Card, Muted } from "./Card";
import styles from "./JobDetail.module.css";
import type { ApplySession, FileEntry } from "./types";

// careeros/apply/session.py OUTCOMES
const OUTCOMES: CodeTable = {
  submitted: { label: "Submitted", tone: "green" },
  needs_review: { label: "Needs review", tone: "orange" },
  staged: { label: "Staged", tone: "orange" },
  blocked: { label: "Blocked", tone: "red" },
  failed: { label: "Failed", tone: "red" },
};

const THUMB_W = 120;
const THUMB_H = 72;
// Apply screenshots are taken at the browser's window size; this box keeps the layout steady while loading.
const FULL_W = 1280;
const FULL_H = 800;

function shotName(name: string): string {
  return name.replace(/\.[a-z0-9]+$/i, "").replace(/[_-]+/g, " ");
}

function ScreenshotViewer({
  jobId,
  shots,
  index,
  onIndex,
  onClose,
}: {
  jobId: string;
  shots: FileEntry[];
  index: number | null;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const n = shots.length;
  const i = index ?? 0;
  const shot = shots[i];
  const go = (d: number) => onIndex((i + d + n) % n);
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      go(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      go(1);
    }
  }
  return (
    <Dialog
      open={index !== null && !!shot}
      onClose={onClose}
      title={`Screenshot ${i + 1} of ${n}`}
      description={shot ? shotName(shot.name) : undefined}
      className={styles.viewer}
    >
      <div className={styles.viewerBody} onKeyDown={onKeyDown}>
        {shot ? (
          <img
            src={fileUrl(jobId, `screenshots/${shot.name}`)}
            alt={`Apply step screenshot ${i + 1} of ${n}: ${shotName(shot.name)}`}
            width={FULL_W}
            height={FULL_H}
            className={styles.viewerImg}
          />
        ) : null}
        <div className={styles.viewerNav}>
          <Button size="small" icon={<ChevronLeft size={14} aria-hidden="true" />} onClick={() => go(-1)} disabled={n < 2}>
            Previous
          </Button>
          <span className={styles.caption}>Use the arrow keys to move between screenshots.</span>
          <Button size="small" onClick={() => go(1)} disabled={n < 2}>
            Next
            <ChevronRight size={14} aria-hidden="true" />
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

export function ApplySessionCard({
  jobId,
  session,
  screenshots,
}: {
  jobId: string;
  session: ApplySession | null;
  screenshots: FileEntry[];
}) {
  const [open, setOpen] = useState<number | null>(null);
  const steps = session?.steps ?? [];
  const outcome = session ? (session.outcome ? describeCode(OUTCOMES, session.outcome) : { label: "In progress", tone: "blue" as const }) : null;
  const started = formatDateTime(session?.started);

  return (
    <Card
      title="Apply session"
      aside={
        session ? (
          <span className={styles.qaVerdict}>
            {outcome ? <Chip tone={outcome.tone}>{outcome.label}</Chip> : null}
            {started ? <span className={styles.caption}>{started}</span> : null}
          </span>
        ) : undefined
      }
    >
      {!session ? <Muted>No apply session yet. Apply runs stop before submit for you to check.</Muted> : null}
      {steps.length ? (
        <ol className={styles.steps}>
          {steps.map((s, i) => (
            <li key={i} className={styles.stepRow}>
              <span aria-hidden="true" className={styles.stepNo}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <span aria-hidden="true" className={styles.stepDot} data-ok={s.ok} />
              <span className={styles.grow}>
                <span className="sr-only">{s.ok ? "Done: " : "Stopped: "}</span>
                {s.action}
                {s.note ? <span className={styles.sec}> · {s.note}</span> : null}
              </span>
            </li>
          ))}
        </ol>
      ) : session ? (
        <Muted>No steps recorded.</Muted>
      ) : null}
      {session?.reason ? <Muted>{session.reason}</Muted> : null}
      {screenshots.length ? (
        <ul className={styles.thumbs} aria-label="Screenshots">
          {screenshots.map((f, i) => (
            <li key={f.name}>
              <button
                type="button"
                className={styles.thumb}
                aria-haspopup="dialog"
                aria-label={`Open screenshot ${i + 1} of ${screenshots.length}: ${shotName(f.name)}`}
                onClick={() => setOpen(i)}
              >
                <img
                  src={fileUrl(jobId, `screenshots/${f.name}`)}
                  alt={`Screenshot ${i + 1}: ${shotName(f.name)}`}
                  width={THUMB_W}
                  height={THUMB_H}
                  loading="lazy"
                />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <ScreenshotViewer jobId={jobId} shots={screenshots} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
    </Card>
  );
}
