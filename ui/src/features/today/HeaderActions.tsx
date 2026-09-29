import { RotateCw, Zap } from "lucide-react";
import { useId, useState } from "react";
import { scoutProgress, useStepRun } from "../runs/useStepRun";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { errorText, useMeta, usePrepareQueued } from "./api";
import type { TodayData } from "./types";
import styles from "./Today.module.css";

interface Props {
  queue: TodayData["prepare_queue"] | undefined;
  paused: boolean;
}

function prepareBlocked(queue: Props["queue"], paused: boolean): string | null {
  if (paused) return "Runs are paused.";
  if (!queue) return null; // still loading: disabled without a reason
  if (queue.total === null || queue.total === undefined) return queue.error || "The prepare queue can’t be read right now.";
  if (queue.total === 0) return "Nothing is queued to prepare.";
  return null;
}

/** "Run scout" and "Prepare queued (N)": each starts a run on the server; refusals show the server's reason. */
export function HeaderActions({ queue, paused }: Props) {
  const toast = useToast();
  const meta = useMeta();
  const [viewing, setViewing] = useState(false);
  const scout = useStepRun("scout", undefined, (run) => {
    setViewing(false);
    if (run.stop_reason !== "cancelled") toast.show({ message: run.stop_reason === "completed" ? "Scout finished." : `Scout stopped: ${run.detail || run.stop_reason}` });
  });
  const progress = scoutProgress(scout.run);
  const prepare = usePrepareQueued();
  const reasonId = useId();
  const total = queue?.total;
  const reason = prepareBlocked(queue, paused);

  return (
    <div className={styles.headerActions}>
      <div className={styles.headerButtons}>
        {scout.running ? (
          <Button icon={<RotateCw size={14} strokeWidth={1.7} aria-hidden="true" />} onClick={() => setViewing(true)}>
            View scout progress
          </Button>
        ) : (
          <Button
            icon={<RotateCw size={14} strokeWidth={1.7} aria-hidden="true" />}
            pending={scout.start.isPending}
            pendingLabel="Starting…"
            onClick={() =>
              scout.start.mutate(undefined, {
                onSuccess: () => setViewing(true),
                onError: (e) => toast.show({ message: `Couldn’t start scout: ${errorText(e)}` }),
              })
            }
          >
            Run scout
          </Button>
        )}
        <Button
          variant="primary"
          icon={<Zap size={14} strokeWidth={1.7} aria-hidden="true" />}
          pending={prepare.isPending}
          pendingLabel="Starting…"
          disabled={!queue || reason !== null}
          aria-describedby={reason ? reasonId : undefined}
          onClick={() =>
            prepare.mutate(meta.data?.presets?.recommended, {
              onSuccess: () => toast.show({ message: "Prepare started." }),
              onError: (e) => toast.show({ message: `Couldn’t start prepare: ${errorText(e)}` }),
            })
          }
        >
          {typeof total === "number" ? `Prepare queued (${formatCount(total)})` : "Prepare queued"}
        </Button>
      </div>
      {scout.running && viewing ? (
        <section className={styles.reason} aria-label="Scout progress">
          <p role="status">
            {progress.step} · {formatCount(progress.found)} found so far · {progress.elapsed}s
          </p>
          <Button size="small" onClick={() => scout.stop()}>
            Cancel
          </Button>{" "}
          <Button size="small" onClick={() => setViewing(false)}>
            Back
          </Button>
        </section>
      ) : null}
      {reason ? (
        <p id={reasonId} className={styles.reason}>
          {reason}
        </p>
      ) : null}
    </div>
  );
}
