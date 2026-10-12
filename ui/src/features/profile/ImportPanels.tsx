import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import type { Tone } from "../../kit/labels";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiSend } from "../../api/client";
import { errorText } from "../today/api";
import { restoreDropped, retryImport, useImport, useProfileWrite, type ResumeStatus } from "./api";
import styles from "./Profile.module.css";

const STATUS: Record<ResumeStatus, [string, Tone]> = {
  reviewing: ["Reviewing", "blue"], draft: ["Draft", "orange"], ready: ["Ready", "green"], failed: ["Failed", "red"],
};

/** Profile › Résumés row state (REQ-125). Text + tone, never colour alone. */
export function StatusBadge({ status }: { status?: ResumeStatus }) {
  if (!status || !STATUS[status]) return null;
  const [label, tone] = STATUS[status];
  return <Chip tone={tone}>{label}</Chip>;
}

/** Failed import: the original upload is kept; Retry re-runs the import (DEC-019). */
export function RetryImport({ rid }: { rid: string }) {
  const retry = useProfileWrite(retryImport);
  return (
    <>
      <Button size="small" pending={retry.isPending} pendingLabel="Retrying…" onClick={() => retry.mutate(rid)}>Retry import</Button>
      {retry.isError ? <p role="alert" className={styles.banner}>{errorText(retry.error)}</p> : null}
    </>
  );
}

/**
 * "Not carried over" (DEC-019): lines the import left out, each restorable into the draft. Self-contained so the
 * workspace page can mount it as well as Profile › résumé.
 */
export function NotCarriedOver({ rid }: { rid: string }) {
  const q = useImport(rid);
  const restore = useProfileWrite(restoreDropped);
  const dropped = q.data?.dropped ?? [];
  if (!dropped.length) return null;
  return (
    <section className={styles.card} aria-labelledby={`nco-${rid}`}>
      <h2 id={`nco-${rid}`} className={styles.h2}>Not carried over</h2>
      <p className={styles.muted}>These lines from your upload weren’t added to your résumé. Restore any you want to keep.</p>
      <ul className={styles.list}>
        {dropped.map((d) => (
          <li key={d.id} className={styles.row}>
            <span className={styles.grow}>{d.text}</span>
            {d.restored ? <Chip tone="green">Restored</Chip> : (
              <Button size="small" aria-label={`Restore ${d.text}`} pending={restore.isPending && restore.variables?.did === d.id}
                pendingLabel="Restoring…" onClick={() => restore.mutate({ rid, did: d.id })}>Restore</Button>
            )}
          </li>
        ))}
      </ul>
      {restore.isError ? <p role="alert" className={styles.banner}>{errorText(restore.error)}</p> : null}
    </section>
  );
}

/**
 * Onboarding "Next" (FLOW-001): publish as master, then continue. The caller supplies `flush` (save pending
 * edits; false = failed, don't publish) and `onDone` (navigate). Open suggestions don't block.
 */
export function NextButton({ rid, flush, onDone, label = "Next: Saved answers →" }:
  { rid: string; flush: () => Promise<boolean>; onDone: () => void; label?: string }) {
  const qc = useQueryClient();
  const next = useMutation({
    mutationFn: async () => {
      if (!(await flush())) throw new Error("Save your changes first (Retry save).");
      return apiSend<unknown>("POST", `/api/profile/resumes/${encodeURIComponent(rid)}/publish`,
        { key: crypto.randomUUID(), master: true });
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["profile"] }); void qc.invalidateQueries({ queryKey: ["readiness"] }); onDone(); },
  });
  return (
    <>
      <Button variant="primary" pending={next.isPending} pendingLabel="Saving…" onClick={() => next.mutate()}>{label}</Button>
      {next.isError ? <p role="alert" className={styles.banner}>{errorText(next.error)}</p> : null}
    </>
  );
}
