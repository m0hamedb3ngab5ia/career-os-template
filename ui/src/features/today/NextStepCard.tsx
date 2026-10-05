import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiFetch } from "../../api/client";
import { Button, ButtonLink } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { useReadiness } from "../profile/api";
import { useStepRun } from "../runs/useStepRun";
import { errorText } from "./api";
import styles from "../profile/Profile.module.css";

interface NextStep {
  key: "finish_setup" | "find_jobs" | "pick_jobs" | "see_progress" | "start_pipeline";
  label: string;
  href: string | null;
}

const WHY: Record<NextStep["key"], string> = {
  finish_setup: "Finish the setup checklist before you apply.",
  find_jobs: "No jobs yet. Run scout to find some.",
  pick_jobs: "Tick the jobs you want the pipeline to work on.",
  see_progress: "A batch is running.",
  start_pipeline: "Your ticked jobs are ready for the pipeline.",
};

/** REQ-122: one "Next step" card with one button, from GET /api/next-step. Hidden while loading or on error. */
export function NextStepCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const step = useQuery({ queryKey: ["next-step"], queryFn: () => apiFetch<NextStep>("/api/next-step") });
  const scout = useStepRun("scout", undefined, () => void qc.invalidateQueries({ queryKey: ["next-step"] }));
  const s = step.data;
  if (!s) return null;
  return (
    <section className={styles.card} aria-labelledby="next-step-h">
      <h2 id="next-step-h" className={styles.h2}>Next step</h2>
      <p className={styles.muted}>{WHY[s.key]}</p>
      <p>
        {s.href ? (
          <ButtonLink to={s.href} variant="primary" size="regular">{s.label}</ButtonLink>
        ) : (
          <Button
            variant="primary"
            pending={scout.start.isPending || scout.running}
            pendingLabel="Finding jobs…"
            onClick={() => scout.start.mutate(undefined, { onError: (e) => toast.show({ message: `Couldn’t start scout: ${errorText(e)}` }) })}
          >
            {s.label}
          </Button>
        )}
      </p>
    </section>
  );
}

/** REQ-122 on Profile: the card appears once, when the last must-have closes while the page is open. */
export function JustReadyNextStep() {
  const ready = useReadiness().data?.ready;
  const [was, setWas] = useState(ready);
  const [shown, setShown] = useState(false);
  if (ready !== was) {
    setWas(ready);
    if (was === false && ready === true) setShown(true);
  }
  return shown ? <NextStepCard /> : null;
}
