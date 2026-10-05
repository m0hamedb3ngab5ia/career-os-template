import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { Details } from "../../kit/Details";
import { TextInput } from "../../kit/inputs";
import { errorText } from "../today/api";
import {
  applyFeedback, approveMaster, refreshMaster, useLearnRun, useMasterRun, retryReview, commentFeedback, dismissFeedback, rejectMaster, useFeedback, useMasterProposal, useProfileWrite,
  type FeedbackItem,
} from "./api";
import styles from "./Profile.module.css";

const lineClass = (l: string) => (l.startsWith("+") && !l.startsWith("+++") ? styles.add : l.startsWith("-") && !l.startsWith("---") ? styles.del : undefined);

/** REQ-099 panel: the proposed master.yaml diff with Approve / Reject; readiness `master_synced` links here. */
export function MasterSyncPanel() {
  const [stale, setStale] = useState(false);
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
  return (
    <section id="master" className={styles.card} aria-labelledby="master-h">
      <h2 id="master-h" className={styles.h2}>master.yaml sync</h2>
      <p className={styles.muted}>The applier types from profile/master.yaml. Changes taken from your master résumé wait here for your OK.</p>
      {q.isPending ? <p className={styles.muted}>Loading…</p> : null}
      {q.isError ? <p className={styles.muted}>Couldn’t load: {errorText(q.error)} <Button size="small" onClick={() => void q.refetch()}>Try again</Button></p> : null}
      {failed ? <p role="alert" className={styles.banner}>{errorText(failed.error)}</p> : null}
      {p?.state === "synced" ? <p role="status">In sync with your master résumé.</p> : null}
      {p?.state === "stale" && (reading || run.isPending) ? <p role="status">Reading your master résumé… a proposed change appears here when it’s ready.</p> : null}
      {p?.state === "stale" && !reading && !run.isPending ? (
        <p role="status">
          Couldn’t read your master résumé.{" "}
          <Button size="small" pending={reread.isPending} pendingLabel="Starting…" onClick={() => reread.mutate()}>Re-read</Button>
        </p>
      ) : null}
      {p?.state === "rejected" ? <p role="status">You rejected the last proposal; master.yaml is unchanged. Upload a new master version to get a new one.</p> : null}
      {p?.state === "pending" || p?.state === "rejected" ? (
        <pre className={styles.diff} aria-label="Proposed master.yaml changes">
          {p.diff.split("\n").map((l, i) => <span key={i} className={lineClass(l)}>{l}{"\n"}</span>)}
        </pre>
      ) : null}
      {p?.state === "pending" ? (
        <p>
          <Button size="small" variant="primary" pending={approve.isPending} pendingLabel="Approving…" onClick={() => approve.mutate()}>Approve changes</Button>{" "}
          <Button size="small" pending={reject.isPending} pendingLabel="Rejecting…" onClick={() => reject.mutate()}>Reject</Button>
        </p>
      ) : null}
    </section>
  );
}

function FeedbackRow({ rid, it }: { rid: string; it: FeedbackItem }) {
  const [note, setNote] = useState("");
  const apply = useProfileWrite(applyFeedback);
  const dismiss = useProfileWrite(dismissFeedback);
  const comment = useProfileWrite(commentFeedback);
  const failed = [apply, dismiss, comment].find((m) => m.isError);
  const open = it.state === "open";
  // Apply starts a resume_edit run; the item stays open until it ends, so follow the run, then refetch feedback.
  const [run, setRun] = useState<string | null>(null);
  const follow = useLearnRun(run);
  const ended = follow.isError || (!!follow.data && follow.data.state !== "running");
  const qc = useQueryClient();
  useEffect(() => {
    if (run && ended) { setRun(null); void qc.invalidateQueries({ queryKey: ["profile", "feedback", rid] }); }
  }, [run, ended, qc, rid]);
  return (
    <li className={styles.row}>
      <span className={styles.grow}>
        <strong>{it.section}</strong> · {it.issue}
        <br />
        <span className={styles.muted}>Suggestion: {it.suggestion}</span>
        {(it.comments ?? []).map((c, i) => <span key={i} className={styles.muted}><br />Your comment: {c.text}</span>)}
        {open ? null : <span className={styles.muted}> · {it.state === "redrafting" ? "redrafting…" : it.state}</span>}
        {open && it.reason ? <span role="status"> · Not applied: {it.reason}</span> : null}
        {failed ? <span role="alert"> Couldn’t do that: {errorText(failed.error)}</span> : null}
      </span>
      {open ? (
        <>
          <Button size="small" variant="primary" pending={apply.isPending || !!run} pendingLabel="Applying…"
            onClick={() => apply.mutate({ rid, fid: it.id }, { onSuccess: (r) => setRun(r.run_id ?? null) })}>Apply</Button>
          <Button size="small" pending={dismiss.isPending} pendingLabel="Dismissing…" onClick={() => dismiss.mutate({ rid, fid: it.id })}>Dismiss</Button>
          <span className={styles.comment}>
            <TextInput aria-label={`Comment on ${it.section}`} placeholder="Comment to redraft" value={note} onValueChange={setNote} />
            <Button size="small" disabled={!note.trim()} title={note.trim() ? undefined : "Type a comment first"} pending={comment.isPending} pendingLabel="Sending…"
              onClick={() => comment.mutate({ rid, fid: it.id, text: note.trim() }, { onSuccess: () => setNote("") })}>Send</Button>
          </span>
        </>
      ) : null}
    </li>
  );
}

/** REQ-094..096: a résumé's review feedback, collapsed until opened (open items first). */
export function ResumeFeedback({ rid }: { rid: string }) {
  const { data } = useFeedback(rid);
  const retry = useProfileWrite(retryReview);
  if (!data || (!data.review && !data.items.length)) return null;
  const open = data.items.filter((i) => i.state === "open").length;
  const items = [...data.items].sort((a, b) => Number(b.state === "open") - Number(a.state === "open"));
  return (
    <div className={styles.full}>
      {data.review?.state === "running" ? <p role="status" className={styles.muted}>Reviewing this résumé…{data.review.run ? <> <Link to={`/runs/${encodeURIComponent(data.review.run)}`}>See progress</Link></> : null}</p> : null}
      {data.review?.state === "failed" ? (
        <p role="status" className={styles.muted}>
          The review failed.{" "}
          <Button size="small" pending={retry.isPending} pendingLabel="Starting…" onClick={() => retry.mutate(rid)}>Retry review</Button>
        </p>
      ) : null}
      {items.length ? (
        <Details summary={`Feedback: ${open} open of ${items.length}`}>
          <ul className={styles.list}>{items.map((it) => <FeedbackRow key={it.id} rid={rid} it={it} />)}</ul>
        </Details>
      ) : null}
    </div>
  );
}
