import { useState } from "react";
import { Link } from "react-router";
import { Button, ButtonLink } from "../../kit/Button";
import { useToast } from "../../kit/Toast";
import { useMeta } from "../../api/meta";
import { errorText, usePipeline, useSetStatus, useStartPipeline } from "../job-detail/api";
import type { components } from "../../api/schema.gen";
import styles from "./Today.module.css";

type Pick = components["schemas"]["JobListItem"];

/** REQ-130 reasons line: "<covered>/<total> skills · missing: <top 2>, +n"; null = not computed yet. */
export function reasonsLine(r: Pick["reasons"]): string {
  if (!r) return "Match pending";
  const head = `${r.covered}/${r.total} skills`;
  if (!r.missing.length) return head;
  const more = r.missing.length > 2 ? `, +${r.missing.length - 2}` : "";
  return `${head} · missing: ${r.missing.slice(0, 2).join(", ")}${more}`;
}

/** REQ-127: best-fit new jobs from GET /api/today `top_picks`; a card opens that job. */
export function TopPicks({ picks }: { picks: Pick[] }) {
  return (
    <section className={styles.panel} aria-labelledby="picks-title">
      <div className={styles.panelHead}>
        <h2 id="picks-title" className={styles.h2}>Top picks</h2>
        <Link to="/jobs" className={styles.headLink}>All jobs</Link>
      </div>
      {picks.length ? (
        <ul className={styles.plainList}>
          {picks.map((p) => (
            <PickCard key={p.job_id} pick={p} />
          ))}
        </ul>
      ) : (
        <div className={styles.oneLine}>
          <span>No new picks right now</span>
          <ButtonLink to="/jobs">Browse all jobs</ButtonLink>
        </div>
      )}
    </section>
  );
}

/** One pick: the body opens the job; Prepare starts its one-job run (REQ-127), Skip offers Undo, a failed run shows
 * its cause and Retry. State comes from the Jobs page's own endpoints (GET/POST /api/jobs/{id}/pipeline, /status). */
function PickCard({ pick: p }: { pick: Pick }) {
  const id = p.job_id;
  const toast = useToast();
  const undoSeconds = useMeta().data?.ui?.undo_seconds;
  const start = useStartPipeline(id);
  const setStatus = useSetStatus(id);
  const pipe = usePipeline(id, start.isSuccess);
  const [skipped, setSkipped] = useState(false);
  const failure = pipe.data?.failures?.kind === "prepare" ? pipe.data.failures : null;
  const newRun = start.isSuccess && start.data.run_id !== failure?.last_run;
  const preparing = Boolean(pipe.data?.active_run_id) || start.isPending || newRun;
  const runIt = () => start.mutate({ action: "start" }, { onError: (e) => toast.show({ message: `Couldn’t start: ${errorText(e)}` }) });

  function skip() {
    setStatus.mutate({ status: "skipped" }, {
      onSuccess: (res) => {
        setSkipped(true);
        toast.show({
          message: `Skipped ${p.title}.`,
          seconds: undoSeconds,
          onUndo: () => setStatus.mutate({ status: res.previous ?? "scored" }, {
            onSuccess: () => setSkipped(false),
            onError: (e) => toast.show({ message: `Couldn’t undo: ${errorText(e)}` }),
          }),
        });
      },
      onError: (e) => toast.show({ message: `Couldn’t skip: ${errorText(e)}` }),
    });
  }

  if (skipped) return null;
  return (
    <li>
      <Link to={`/jobs/${encodeURIComponent(id)}`} className={styles.pick}>
        <span className={styles.fit} aria-label={`Fit ${p.fit ?? "unknown"}`}>{p.fit ?? "–"}</span>
        <span className={styles.grow}>
          <span className={styles.strong}>{p.title}</span>
          <span className={styles.caption}>{[p.company, p.location].filter(Boolean).join(" · ")}</span>
          <span className={styles.caption}>{reasonsLine(p.reasons)}</span>
        </span>
      </Link>
      <div className={styles.oneLine}>
        {preparing ? (
          <span role="status">Preparing…</span>
        ) : (
          <>
            {failure && <span className={styles.caption}>Prepare failed: {failure.last_detail || failure.last_outcome || "unknown cause"}</span>}
            <Button variant="primary" size="small" onClick={runIt}>{failure ? "Retry" : "Prepare"}</Button>
            <Button size="small" onClick={skip} pending={setStatus.isPending}>Skip</Button>
          </>
        )}
      </div>
    </li>
  );
}
