import { RotateCw, Zap } from "lucide-react";
import { useId } from "react";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { formatCount } from "../../lib/format";
import { errorText, useMeta, usePrepareQueued, useRunScout } from "./api";
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
  const scout = useRunScout();
  const prepare = usePrepareQueued();
  const reasonId = useId();
  const total = queue?.total;
  const reason = prepareBlocked(queue, paused);

  return (
    <div className={styles.headerActions}>
      <div className={styles.headerButtons}>
        <Button
          icon={<RotateCw size={14} strokeWidth={1.7} aria-hidden="true" />}
          pending={scout.isPending}
          pendingLabel="Starting…"
          onClick={() =>
            scout.mutate(undefined, {
              onSuccess: () => toast.show({ message: "Scout started." }),
              onError: (e) => toast.show({ message: `Couldn’t start scout: ${errorText(e)}` }),
            })
          }
        >
          Run scout
        </Button>
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
      {reason ? (
        <p id={reasonId} className={styles.reason}>
          {reason}
        </p>
      ) : null}
    </div>
  );
}
