import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button } from "../../kit/Button";
import { Dialog } from "../../kit/Dialog";
import { TextInput } from "../../kit/inputs";
import { useResume } from "../runs/api";
import { errorText } from "../today/api";
import {
  applyFeedback, approveMaster, refreshMaster, useLearnRun, useMasterRun, retryReview, commentFeedback, dismissFeedback, rejectMaster, useFeedback, useMasterProposal, useProfileWrite, useResumeVersion,
  type FeedbackItem,
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
export function Passage({ text, quote }: { text: string; quote: string }) {
  const at = text.indexOf(quote);
  if (at < 0) return <pre className={styles.passage}><mark className={styles.hl}>{quote}</mark></pre>;
  const lineStart = text.lastIndexOf("\n", at - 1) + 1;
  const from = lineStart > 0 ? text.lastIndexOf("\n", lineStart - 2) + 1 : 0;
  const lineEnd = text.indexOf("\n", at + quote.length);
  const to = lineEnd < 0 ? text.length : (text.indexOf("\n", lineEnd + 1) + 1 || text.length);
  return (
    <pre className={styles.passage}>
      {text.slice(from, at)}<mark className={styles.hl}>{quote}</mark>{text.slice(at + quote.length, to).replace(/\n$/, "")}
    </pre>
  );
}

/** The résumé lines an item is about: first 2, "See more" for the rest; whole-résumé only when the review says so. */
function BeforeLines({ it, text, onRetry }: { it: FeedbackItem; text?: string; onRetry: () => void }) {
  const [all, setAll] = useState(false);
  const lines = it.quotes?.length ? it.quotes : it.quote ? [it.quote] : [];
  if (it.whole) return <p>This affects the whole résumé, not one line.</p>;
  // items from a review made before quotes were saved: re-run it to get the lines
  if (!lines.length) return <p>Review again to see the exact lines. <Button size="small" onClick={onRetry}>Review again</Button></p>;
  const more = lines.length - 2;
  return (
    <>
      {(all ? lines : lines.slice(0, 2)).map((q, i) => text === undefined ? <p key={i}>{q}</p> : <Passage key={i} text={text} quote={q} />)}
      {more > 0 ? <button type="button" className={styles.link} aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Collapse" : `See more (${more})`}</button> : null}
    </>
  );
}

/** One suggestion: Before passage vs Suggested change. Content: Accept (queued apply) / Ignore; format: Mark as fixed / Ignore. */
function FeedbackStep({ rid, it, text, applying, onAccept, onDone, onRetry }: {
  rid: string; it: FeedbackItem; text?: string; applying: "applying" | "waiting" | null; onAccept: () => void; onDone: () => void; onRetry: () => void;
}) {
  const [note, setNote] = useState("");
  const [wording, setWording] = useState(false);
  const dismiss = useProfileWrite(dismissFeedback);
  const comment = useProfileWrite(commentFeedback);
  const failed = [dismiss, comment].find((m) => m.isError);
  const open = it.state === "open";
  const format = it.kind === "format";
  const ignore = () => dismiss.mutate({ rid, fid: it.id }, { onSuccess: onDone });
  return (
    <div className={styles.note}>
      <p><strong>{it.section}:</strong> {it.issue}</p>
      <div className={styles.compare}>
      <div className={`${styles.box} ${styles.beforeBox}`}>
        <h4>Before</h4>
        <BeforeLines it={it} text={text} onRetry={onRetry} />
      </div>
      <div className={`${styles.box} ${styles.afterBox}`}>
        <h4>{format ? "How to fix" : "Suggested change"}</h4>
        <p>{it.suggestion}</p>
      </div>
      </div>
      {(it.comments ?? []).map((c, i) => <p key={i} className={styles.muted}>Your comment: {c.text}</p>)}
      {open ? null : <p role="status" className={styles.muted}>{it.state === "redrafting" ? "Redrafting…" : it.state === "applied" ? `Applied (v${it.applied_v})` : "Dismissed"}</p>}
      {open && it.reason ? <p role="status">Not applied: {it.reason}</p> : null}
      {failed ? <p role="alert">Couldn’t do that: {errorText(failed.error)}</p> : null}
      {open ? (
        <>
          <p className={styles.actions}>
            {format ? (
              <Button size="small" variant="primary" pending={dismiss.isPending} pendingLabel="Saving…" onClick={ignore}>Mark as fixed</Button>
            ) : (
              <Button size="small" variant="primary" pending={!!applying} pendingLabel={applying === "waiting" ? "Waiting…" : "Applying…"}
                onClick={onAccept}>Accept</Button>
            )}
            <Button size="small" pending={dismiss.isPending} pendingLabel="Ignoring…" onClick={ignore}>Ignore</Button>
          </p>
          {format ? null : wording ? (
            <span className={styles.comment}>
              <TextInput aria-label={`Comment on ${it.section}`} placeholder="What should it say instead?" value={note} onValueChange={setNote} />
              <Button size="small" disabled={!note.trim()} title={note.trim() ? undefined : "Type a comment first"} pending={comment.isPending} pendingLabel="Sending…"
                onClick={() => comment.mutate({ rid, fid: it.id, text: note.trim() }, { onSuccess: () => setNote("") })}>Send</Button>
            </span>
          ) : (
            <button type="button" className={styles.link} onClick={() => setWording(true)}>Suggest different wording</button>
          )}
        </>
      ) : null}
    </div>
  );
}

/** Review popup: one suggestion at a time; Accept/Ignore move on, closing = review the rest later. */
function FeedbackDialog({ rid, latest, items, onClose, onRetry }: {
  rid: string; latest: number; items: FeedbackItem[]; onClose: () => void; onRetry: () => void;
}) {
  const [i, setI] = useState(0);
  const text = useResumeVersion(rid, latest);
  // Accept starts a resume_edit run; only one run at a time, so Accepts made while one runs wait in `queue`.
  // The item stays open until its run ends: follow the run, refetch, then start the next queued Accept.
  const apply = useProfileWrite(applyFeedback);
  const [queue, setQueue] = useState<string[]>([]);
  const [pending, setPending] = useState<{ fid: string; run: string } | null>(null);
  const follow = useLearnRun(pending?.run ?? null);
  const ended = follow.isError || (!!follow.data && follow.data.state !== "running");
  const qc = useQueryClient();
  const busy = !!pending || apply.isPending;
  useEffect(() => {
    if (pending && ended) { setPending(null); void qc.invalidateQueries({ queryKey: ["profile"] }); }
  }, [pending, ended, qc]);
  const { mutate } = apply;
  useEffect(() => {
    const [fid, ...rest] = queue;
    if (busy || fid === undefined) return;
    setQueue(rest);
    mutate({ rid, fid }, { onSuccess: (r) => { if (r.run_id) setPending({ fid, run: r.run_id }); } });
  }, [busy, queue, rid, mutate]);
  const status = (fid: string) =>
    pending?.fid === fid || (apply.isPending && apply.variables?.fid === fid) ? "applying" as const : queue.includes(fid) ? "waiting" as const : null;
  const n = Math.min(i, items.length - 1);
  const it = items[n];
  if (!it) return null;
  const next = () => setI((k) => Math.min(k + 1, items.length - 1));
  return (
    <Dialog open onClose={onClose} title="Résumé review" className={styles.review}
      description={`CareerOS found ${items.length} possible improvement${items.length === 1 ? "" : "s"}`}>
      <p className={styles.step}>
        <span>Suggestion {n + 1} of {items.length}</span>
        {n > 0 ? <button type="button" className={styles.link} onClick={() => setI(n - 1)}>Back</button> : null}
      </p>
      <progress className={styles.progress} max={items.length} value={n + 1} aria-label="Review progress" />
      {text.isError ? <p className={styles.muted}>Couldn’t load the résumé: {errorText(text.error)}</p> : null}
      {apply.isError ? <p role="alert">Couldn’t apply that suggestion: {errorText(apply.error)}</p> : null}
      <FeedbackStep key={it.id} rid={rid} it={it} text={text.data?.text} applying={status(it.id)}
        onAccept={() => { setQueue((q) => [...q, it.id]); next(); }} onDone={next} onRetry={onRetry} />
    </Dialog>
  );
}

/** REQ-094..096: a résumé's review feedback, reviewed in a popup (open items first). */
export function ResumeFeedback({ rid, latest, master }: { rid: string; latest: number; master?: boolean }) {
  const { data } = useFeedback(rid);
  // the master card shows one failure (in MasterSyncPanel) when the read failed too
  const mp = useMasterProposal(false).data;
  const mrun = useMasterRun(mp?.state === "stale");
  const readFailed = !!master && mp?.state === "stale" && !mrun.isPending && mrun.data?.runs[0]?.state !== "running";
  const retry = useProfileWrite(retryReview);
  const resumeRuns = useResume();
  const [shown, setShown] = useState<FeedbackItem[] | null>(null);
  if (!data || (!data.review && !data.items.length)) return null;
  const open = data.items.filter((i) => i.state === "open").length;
  const items = [...data.items].sort((a, b) => Number(b.state === "open") - Number(a.state === "open"));
  // the popup keeps its order while items change state; their latest data comes from `data`
  const live = shown?.map((s) => data.items.find((d) => d.id === s.id) ?? s);
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
          <Button size="small" variant="primary" onClick={() => setShown(items)}>Review suggestions</Button>
        </p>
      ) : null}
      {live ? <FeedbackDialog rid={rid} latest={latest} items={live} onClose={() => setShown(null)}
        onRetry={() => { retry.mutate(rid); setShown(null); }} /> : null}
    </div>
  );
}
