import { PauseCircle } from "lucide-react";
import { Button } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { formatWhen } from "../../lib/dates";
import { errorText, useResume } from "./api";
import type { PauseState } from "./types";
import styles from "./Today.module.css";

/** "Runs paused until …" with Resume, in the stat row area (docs/UI.md Today). */
export function PausedBanner({ paused, now }: { paused: PauseState; now: Date }) {
  const resume = useResume();
  const toast = useToast();
  const until = formatWhen(paused.until, now);
  return (
    <div className={styles.banner} role="status">
      <span className={styles.bannerIcon}>
        <PauseCircle size={16} strokeWidth={1.7} aria-hidden="true" />
      </span>
      <span className={styles.bannerText}>
        <span className={styles.strong}>{until ? `Runs paused until ${until}` : "Runs paused until you resume"}</span>
        {paused.reason ? <span className={styles.sec}> · {paused.reason}</span> : null}
      </span>
      <Button
        size="small"
        pending={resume.isPending}
        pendingLabel="Resuming…"
        onClick={() =>
          resume.mutate(undefined, {
            onSuccess: () => toast.show({ message: "Runs resumed." }),
            onError: (e) => toast.show({ message: `Couldn’t resume: ${errorText(e)}` }),
          })
        }
      >
        Resume
      </Button>
    </div>
  );
}
