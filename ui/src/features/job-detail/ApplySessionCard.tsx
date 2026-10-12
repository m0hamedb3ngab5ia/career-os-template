import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { Button } from "../../kit/Button";
import { Dialog } from "../../kit/Dialog";
import { fileUrl } from "./api";
import { Card } from "./Card";
import styles from "./JobDetail.module.css";
import type { FileEntry } from "./types";

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
  screenshots,
}: {
  jobId: string;
  screenshots: FileEntry[];
}) {
  const [open, setOpen] = useState<number | null>(null);
  // Only the screenshots are unique here: outcome/reason repeat Next step, steps are run internals (Runs page has
  // the log), fields left are answered in Fill preview.
  if (!screenshots.length) return null;
  return (
    <Card title="Screenshots">
      {(
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
      )}
      <ScreenshotViewer jobId={jobId} shots={screenshots} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
    </Card>
  );
}
