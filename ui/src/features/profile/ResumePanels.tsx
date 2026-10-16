import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { useResume } from "../runs/api";
import { useAnnotations } from "../workspace/api";
import { errorText } from "../today/api";
import {
  approveMaster, refreshMaster, useMasterRun, retryReview, rejectMaster, useFeedback, useMasterProposal, useProfileWrite,
} from "./api";
import styles from "./Profile.module.css";

const lineClass = (l: string) => (l.startsWith("+") && !l.startsWith("+++") ? styles.add : l.startsWith("-") && !l.startsWith("---") ? styles.del : undefined);

/** REQ-099 line in the master card: new details read from the master résumé, Review shows the diff with Approve / Reject; readiness `master_synced` links here. */
export function MasterSyncPanel({ rid }: { rid: string }) {
  const [stale, setStale] = useState(false);
  const reviewFailed = useFeedback(rid).data?.review?.state === "failed";
  const retryRev = useProfileWrite(retryReview);
  const run = useMasterRun(stale);
  const runState = run.data?.runs[0]?.state;
  const reading = runState === "running";
  const q = useMasterProposal(reading);
  const approve = useProfileWrite(approveMaster);
  const reject = useProfileWrite(rejectMaster);
  const reread = useProfileWrite(refreshMaster);
  const failed = [approve, reject, reread].find((m) => m.isError);
  const p = q.isError ? undefined : q.data;
  const refetch = q.refetch;
  useEffect(() => setStale(p?.state === "stale"), [p?.state]);
  useEffect(() => { if (runState && runState !== "running") void refetch(); }, [runState, refetch]); // the run ended: fetch its proposal
  const [open, setOpen] = useState(false);
  if (q.isPending || p?.state === "synced") return null;
  return (
    <div id="master" className={styles.full}>
      {q.isError ? <p className={styles.muted}>Couldn’t load: {errorText(q.error)} <Button size="small" onClick={() => void q.refetch()}>Try again</Button></p> : null}
      {failed ? <p role="alert" className={styles.banner}>{errorText(failed.error)}</p> : null}
      {p?.state === "stale" && (reading || run.isPending) ? <p role="status" className={styles.muted}>Reading your master résumé…</p> : null}
      {p?.state === "stale" && !reading && !run.isPending ? (
        <p role="status" className={styles.muted}>
          We couldn’t process this résumé.{" "}
          <Button size="small" pending={reread.isPending} pendingLabel="Starting…" onClick={() => { reread.mutate(); if (reviewFailed) retryRev.mutate(rid); }}>Retry</Button>
        </p>
      ) : null}
      {p?.state === "pending" || p?.state === "rejected" ? (
        <p role="status" className={styles.muted}>
          {p.state === "pending" ? "CareerOS read new details from this version" : "You rejected the last proposal; your profile facts are unchanged."}{" "}
          <Button size="small" aria-label="Review new details" aria-expanded={open} onClick={() => setOpen(!open)}>Review</Button>
        </p>
      ) : null}
      {open && (p?.state === "pending" || p?.state === "rejected") ? (
        <pre className={styles.diff} aria-label="Proposed profile fact changes">
          {p.diff.split("\n").map((l, i) => <span key={i} className={lineClass(l)}>{l}{"\n"}</span>)}
        </pre>
      ) : null}
      {open && p?.state === "pending" ? (
        <p>
          <Button size="small" variant="primary" pending={approve.isPending} pendingLabel="Approving…" onClick={() => approve.mutate()}>Approve changes</Button>{" "}
          <Button size="small" pending={reject.isPending} pendingLabel="Rejecting…" onClick={() => reject.mutate()}>Reject</Button>
        </p>
      ) : null}
    </div>
  );
}

/** The quote's line with one neighbouring line each side, the quote marked; just the quote if it's not in `text`. */
export function ResumeFeedback({ rid, master }: { rid: string; master?: boolean }) {
  const { data } = useFeedback(rid);
  // the master card shows one failure (in MasterSyncPanel) when the read failed too
  const mp = useMasterProposal(false).data;
  const mrun = useMasterRun(mp?.state === "stale");
  const readFailed = !!master && mp?.state === "stale" && !mrun.isPending && mrun.data?.runs[0]?.state !== "running";
  const retry = useProfileWrite(retryReview);
  const resumeRuns = useResume();
  const ann = useAnnotations(rid).data;
  if (!data || (!data.review && !ann?.length)) return null;
  // suggestions live in the résumé editor (Google-Docs style); old review items show there as comments
  const open = ann?.filter((a) => a.status === "open").length ?? 0;
  return (
    <div className={styles.full}>
      {data.review?.state === "running" ? <p role="status" className={styles.muted}>Reviewing this résumé…{data.review.run ? <> <Link to={`/runs/${encodeURIComponent(data.review.run)}`}>See progress</Link></> : null}</p> : null}
      {data.review?.state === "failed" && !(readFailed && !/paused/.test(data.review.reason ?? "")) ? (
        <p role="status" className={styles.muted}>
          {data.review.reason ? `The review couldn’t start: ${data.review.reason.replace(/^review run not started: /, "")}.` : "We couldn’t process this résumé."}{" "}
          {/paused/.test(data.review.reason ?? "") ? (
            <Button size="small" variant="primary" pending={resumeRuns.isPending || retry.isPending} pendingLabel="Starting…"
              onClick={() => resumeRuns.mutate(undefined, { onSuccess: () => retry.mutate(rid) })}>Resume runs and review</Button>
          ) : (
            <Button size="small" pending={retry.isPending} pendingLabel="Starting…" onClick={() => retry.mutate(rid)}>Retry</Button>
          )}
        </p>
      ) : null}
      {open ? (
        <p className={styles.muted}>
          {open} suggestion{open === 1 ? "" : "s"} to review{" "}
          <Link to={`/resumes/${encodeURIComponent(rid)}`}>Review in editor</Link>
        </p>
      ) : null}
    </div>
  );
}
