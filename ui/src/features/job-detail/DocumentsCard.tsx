import { FileText, FolderOpen } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { Details } from "../../kit/Details";
import { humanize } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { formatBytes, formatCount, formatDate, formatDecimal } from "../../lib/format";
import { help } from "./actionHelp";
import { useStepRun } from "../runs/useStepRun";
import { errorText, fileUrl, useOpenFolder } from "./api";
import { Card } from "./Card";
import styles from "./JobDetail.module.css";
import { DOCUMENTS, RUBRIC_LABELS } from "./labels";
import type { FileEntry, Qa, QaRun } from "./types";

// One row per document; every format of it (resume.pdf, resume.txt) is a link on that row.
type DocGroup = { title: string; order: number; files: FileEntry[] };

function group(files: FileEntry[]): DocGroup[] {
  const out = new Map<string, DocGroup>();
  for (const f of files) {
    const stem = f.name.replace(/\.[^.]+$/, "");
    const i = DOCUMENTS.findIndex((d) => d.match.test(f.name));
    const g = out.get(stem) ?? { title: DOCUMENTS[i]?.title ?? stem, order: i < 0 ? DOCUMENTS.length : i, files: [] };
    g.files.push(f);
    out.set(stem, g);
  }
  const fmt = (f: FileEntry) => ["pdf", "md", "txt"].indexOf(f.name.split(".").pop() ?? "");
  return [...out.values()]
    .map((g) => ({ ...g, files: g.files.toSorted((a, b) => fmt(a) - fmt(b)) }))
    .toSorted((a, b) => a.order - b.order || a.title.localeCompare(b.title));
}

function DocRow({ jobId, doc }: { jobId: string; doc: DocGroup }) {
  const newest = doc.files.reduce((a, b) => ((b.modified ?? "") > (a.modified ?? "") ? b : a));
  const when = formatDate(newest.modified);
  return (
    <li className={styles.docRow}>
      <FileText size={18} strokeWidth={1.6} aria-hidden="true" className={styles.sec} />
      <div className={styles.grow}>
        <div className={styles.strong}>{doc.title}</div>
        {when ? <div className={styles.caption}>Updated {when}</div> : null}
      </div>
      <div className={styles.buttons} role="group" aria-label={`Open ${doc.title}`}>
        {doc.files.map((f) => (
          <a key={f.name} className={styles.buttonLink} href={fileUrl(jobId, f.name)} target="_blank" rel="noopener noreferrer" title={`${f.name} · ${formatBytes(f.size)}`}>
            {(f.name.split(".").pop() ?? "").toUpperCase()}
            <span className="sr-only"> ({f.name}, opens in a new tab)</span>
          </a>
        ))}
      </div>
    </li>
  );
}

function QaSummary({ run }: { run: QaRun }) {
  const s = run.summary ?? {};
  return (
    <div className={styles.qaRun}>
      <span className={styles.strong}>{run.pass ? "QA passed" : "QA failed"}</span>
      {" · "}
      {formatCount(s.hard_fail ?? 0)} hard fails, {formatCount(s.soft_fail ?? 0)} soft fails
      {s.skipped ? `, ${formatCount(s.skipped)} skipped` : ""}
      {run.fail_reasons?.length ? (
        <ul className={styles.bullets}>
          {run.fail_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function QaCard({ jobId, qa, nested }: { jobId: string; qa: Qa | null; nested?: boolean }) {
  const toast = useToast();
  const [result, setResult] = useState<QaRun | null>(null);
  const rerun = useStepRun("qa", jobId, (run) => {
    if (run.stop_reason === "completed" && run.result) setResult(run.result as unknown as QaRun);
    else if (run.stop_reason !== "cancelled") toast.show({ message: run.detail || "QA did not finish." });
  });
  const rubric = Object.entries(qa?.rubric ?? {});
  const verdict = qa ? (qa.pass ? <Chip tone="green">Passed</Chip> : <Chip tone="red">Failed</Chip>) : <Chip tone="gray">Not reviewed</Chip>;
  const meanText = [
    typeof qa?.mean === "number"
      ? typeof qa.threshold === "number"
        ? `${formatDecimal(qa.mean)} of ${formatDecimal(qa.threshold)} needed`
        : `mean ${formatDecimal(qa.mean)}`
      : null,
    qa?.next_action ? `next: ${humanize(qa.next_action).toLowerCase()}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card id="qa" title="QA" nested={nested} aside={<span className={styles.qaVerdict}>{verdict}</span>}>
      {qa?.fail_reasons?.length ? (
        <>
          <ul className={styles.bullets}>
            {qa.fail_reasons.slice(0, 2).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {qa.fail_reasons.length > 2 ? (
            <Details summary={`Show all ${formatCount(qa.fail_reasons.length)} issues`}>
              <ul className={styles.bullets}>
                {qa.fail_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </Details>
          ) : null}
        </>
      ) : null}
      {meanText || rubric.length ? (
        <Details summary="QA scores">
          {meanText ? <p className={styles.caption}>{meanText}</p> : null}
          {rubric.length ? (
            <dl className={styles.rubric}>
              {rubric.map(([k, v]) => (
                <div key={k} className={styles.tile} title={v.why}>
                  <dt>{RUBRIC_LABELS[k] ?? humanize(k)}</dt>
                  <dd>{formatDecimal(v.score)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </Details>
      ) : null}
      <div className={styles.buttons}>
        {rerun.running ? (
          <>
            <span className={styles.caption}>Running QA…</span>
            <Button size="small" onClick={() => rerun.stop()}>
              Stop
            </Button>
          </>
        ) : (
          <Button
            size="small"
            {...help("rerunQa")}
            pending={rerun.start.isPending}
            pendingLabel="Starting…"
            onClick={() => {
              setResult(null);
              rerun.start.mutate(undefined, { onError: (e) => toast.show({ message: errorText(e) }) });
            }}
          >
            Re-run QA
          </Button>
        )}
      </div>
      <div role="status" aria-live="polite">
        {result ? <QaSummary run={result} /> : null}
      </div>
    </Card>
  );
}

export function DocumentsCard({
  jobId,
  documents,
  otherFiles = [],
  submitted,
}: {
  jobId: string;
  documents: FileEntry[];
  otherFiles?: FileEntry[];
  submitted: string[];
}) {
  const toast = useToast();
  const folder = useOpenFolder(jobId);
  const reasonId = useId();
  const docs = group(documents);
  const openFolder = () =>
    folder.mutate(undefined, {
      onSuccess: () => toast.show({ message: "Opened the job folder" }),
      onError: (e) => toast.show({ message: errorText(e) }),
    });
  const latest = submitted.at(-1);

  return (
    <Card
      title="Documents"
      aside={
        <Button
          size="small"
          {...help("openFolder")}
          icon={<FolderOpen size={14} strokeWidth={1.7} aria-hidden="true" />}
          pending={folder.isPending}
          pendingLabel="Opening…"
          onClick={openFolder}
        >
          Open folder
        </Button>
      }
    >
      <ul className={styles.list}>
        {docs.map((f) => (
          <DocRow key={f.title} jobId={jobId} doc={f} />
        ))}
        {docs.length === 0 ? <li className={styles.muted}>No documents yet. Prepare writes them.</li> : null}
        <li className={styles.docRow}>
          <FileText size={18} strokeWidth={1.6} aria-hidden="true" className={styles.sec} />
          <div className={styles.grow}>
            <div className={styles.strong}>Submitted copy</div>
            <div id={reasonId} className={styles.caption}>
              {latest
                ? `Frozen when you submitted · ${latest}`
                : "Available after you submit · freezes files, answers as typed and the posting"}
            </div>
          </div>
          {latest ? (
            <Button size="small" {...help("showInFolder")} onClick={openFolder}>
              Show in folder
            </Button>
          ) : (
            <Button size="small" disabled aria-describedby={reasonId}>
              View submitted copy
            </Button>
          )}
        </li>
      </ul>
      {otherFiles.length ? (
        <Details summary={`All files (${formatCount(otherFiles.length)})`}>
          <ul className={styles.list} aria-label="All files">
            {otherFiles.toSorted((a, b) => a.name.localeCompare(b.name)).map((f) => (
              <li key={f.name} className={styles.docRow}>
                <div className={styles.grow}>
                  <a translate="no" href={fileUrl(jobId, f.name)} target="_blank" rel="noopener noreferrer">
                    {f.name}
                    <span className="sr-only"> (opens in a new tab)</span>
                  </a>
                  <div className={styles.caption}>{formatBytes(f.size)}{formatDate(f.modified) ? ` · ${formatDate(f.modified)}` : ""}</div>
                </div>
              </li>
            ))}
          </ul>
        </Details>
      ) : null}
    </Card>
  );
}
