import { Check, X } from "lucide-react";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";
import { Button } from "../../kit/Button";
import { formatDate } from "../../lib/format";
import { errorText } from "../today/api";
import { fileUrl, useDecide, useJobDetail, useJobPipeline, useJobText, type JobDetail } from "./api";
import { OutreachBlock } from "./OutreachBlock";
import { deriveSteps, withoutFrontmatter } from "./steps";
import styles from "./JobInspector.module.css";

const DONE = ["applied", "screening", "interview", "offer", "rejected", "withdrawn", "ghosted"];

/** Open/close the inspector from anywhere: sets `?job=<id>`, keeping the rest of the URL. */
export function useInspector() {
  const [params, setParams] = useSearchParams();
  const id = params.get("job");
  const set = (next: string | null) =>
    setParams(
      (p) => {
        const q = new URLSearchParams(p);
        if (next) q.set("job", next);
        else q.delete("job");
        return q;
      },
      { replace: !next },
    );
  return { id, open: (jobId: string) => set(jobId), close: () => set(null) };
}

/** Click handler for a job row: opens the inspector unless the click landed on a link, button or field. */
export function useRowOpen() {
  const { open } = useInspector();
  return (id: string) => (e: { target: EventTarget }) => {
    if (!(e.target instanceof Element) || e.target.closest("a,button,input,label,select,textarea")) return;
    open(id);
  };
}

/** Right-side panel on wide screens, full-screen sheet on narrow ones. Rendered once, by AppShell. */
export function JobInspector() {
  const { id, close } = useInspector();
  if (!id) return null;
  return <Panel key={id} id={id} onClose={close} />;
}

const pick = (files: string[], re: RegExp) => files.find((f) => re.test(f));

function Panel({ id, onClose }: { id: string; onClose: () => void }) {
  const detail = useJobDetail(id);
  const closeBtn = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !e.defaultPrevented && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [onClose]);
  const d = detail.data;
  return (
    <div className={styles.panel} role="dialog" aria-modal="true" aria-labelledby="job-inspector-title">
      <header className={styles.head}>
        <div>
          <h2 id="job-inspector-title" className={styles.title}>{d?.job?.title ?? (detail.isError ? "Job not found" : "Loading…")}</h2>
          {d?.job?.company ? <p className={styles.company}>{d.job.company}</p> : null}
        </div>
        <button ref={closeBtn} type="button" className={styles.close} onClick={onClose} aria-label="Close details">
          <X size={16} aria-hidden="true" />
        </button>
      </header>
      {detail.isError ? <p className={styles.error}>{errorText(detail.error)}</p> : null}
      {d ? <Body id={id} d={d} onDone={onClose} /> : null}
    </div>
  );
}

function Body({ id, d, onDone }: { id: string; d: JobDetail; onDone: () => void }) {
  const job = d.job;
  const files = d.documents.map((f) => f.name);
  // outreach.json / contacts.json are listed under other_files, not documents.
  const allFiles = [...files, ...(d.other_files ?? []).map((f) => f.name)];
  const qa = d.qa as { pass?: unknown; passed?: unknown } | null | undefined;
  const qaFlag = qa?.pass ?? qa?.passed;
  const qaPassed = typeof qaFlag === "boolean" ? qaFlag : null;
  const status = d.status ?? job?.status ?? null;
  const steps = deriveSteps({ status, fit: job?.fit, files, qaPassed });
  const resumeTxt = pick(files, /^resume\.txt$/);
  const resumePdf = pick(files, /^resume\.pdf$/);
  const letter = pick(files, /^cover_letter\.(txt|md)$/) ?? pick(files, /^cover_letter\.pdf$/);
  const resume = useJobText(id, resumeTxt);
  const letterText = useJobText(id, letter && !letter.endsWith(".pdf") ? letter : undefined);
  const decide = useDecide(id);
  const pipeline = useJobPipeline(id).data;
  // Tier A is never auto-submitted (hard rule), whatever the pipeline note says.
  const stagesOnly = d.job?.tier === "A" ? true : pipeline ? pipeline.auto_submit === false || /^Tier A/.test(pipeline.note ?? "") : null;
  const approveNote =
    stagesOnly === null
      ? "Approve marks it ready for the next apply run."
      : stagesOnly
        ? "You’ll submit it yourself."
        : "The next apply run may submit it automatically (auto-submit is on for this tier).";
  const posted = typeof d.posting.posted_at === "string" ? formatDate(d.posting.posted_at) : null;
  const found = formatDate(job?.found_at);
  const reasons = Array.isArray(d.qa?.fail_reasons) ? (d.qa.fail_reasons as unknown[]).map(String) : [];
  const drafted = steps[1]?.state === "done";
  const finished = DONE.includes(status ?? "") || status === "skipped";
  const canApprove = drafted && !finished && status !== "queued" && qaPassed === true;

  return (
    <div className={styles.body}>
      <dl className={styles.facts}>
        <div><dt>Posted</dt><dd>{posted ?? "Not listed"}</dd></div>
        <div><dt>Found</dt><dd>{found ?? "Unknown"}</dd></div>
        <div><dt>Fit</dt><dd>{job?.fit != null ? `${job.fit}%` : "Not scored"}</dd></div>
      </dl>
      {job?.url ? (
        <a className={styles.posting} href={job.url} target="_blank" rel="noopener noreferrer">Open the posting</a>
      ) : null}

      <ol className={styles.steps} aria-label="Progress">
        {steps.map((s) => (
          <li key={s.label} data-state={s.state} aria-current={s.state === "current" ? "step" : undefined}>
            <span className={styles.mark} aria-hidden="true">{s.state === "done" ? <Check size={11} strokeWidth={3} /> : null}</span>
            {s.label}
            {s.state === "failed" ? <span className="sr-only"> (didn’t pass)</span> : null}
          </li>
        ))}
      </ol>

      {reasons.length ? (
        <section aria-label="Why the quality check failed">
          <h3 className={styles.h3}>Why it didn’t pass</h3>
          <ul className={styles.reasons}>{reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </section>
      ) : null}

      {resumeTxt || resumePdf ? (
        <section aria-label="Résumé">
          <h3 className={styles.h3}>Résumé</h3>
          {resumePdf ? <a className={styles.posting} href={fileUrl(id, resumePdf)} target="_blank" rel="noopener noreferrer">Open the PDF</a> : null}
          {resume.data ? <pre className={styles.text}>{resume.data}</pre> : null}
        </section>
      ) : null}
      {letter ? (
        <section aria-label="Cover letter">
          <h3 className={styles.h3}>Cover letter</h3>
          {letter.endsWith(".pdf") ? <a className={styles.posting} href={fileUrl(id, letter)} target="_blank" rel="noopener noreferrer">Open the PDF</a> : null}
          {letterText.data ? <pre className={styles.text}>{withoutFrontmatter(letterText.data)}</pre> : null}
        </section>
      ) : null}
      <OutreachBlock id={id} files={allFiles} />
      {!drafted && !finished ? <p className={styles.muted}>No résumé or cover letter yet.</p> : null}

      {decide.isError ? <p className={styles.error}>{errorText(decide.error)}</p> : null}
      {!finished ? (
        <footer className={styles.actions}>
          {canApprove ? (
            <Button variant="primary" pending={decide.isPending && decide.variables === "approve"} pendingLabel="Approving…"
              onClick={() => decide.mutate("approve", { onSuccess: onDone })}>
              Approve
            </Button>
          ) : null}
          <Button pending={decide.isPending && decide.variables === "skip"} pendingLabel="Skipping…"
            onClick={() => decide.mutate("skip", { onSuccess: onDone })}>
            Skip
          </Button>
          {canApprove ? <p className={styles.muted}>{approveNote}</p> : null}
        </footer>
      ) : null}
    </div>
  );
}
