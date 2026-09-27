import { FileText, FolderOpen } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip } from "../../kit/chips";
import { humanize } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { formatBytes, formatCount, formatDate, formatDecimal } from "../../lib/format";
import { help } from "./actionHelp";
import { errorText, fileUrl, useOpenFolder, useRerunQa } from "./api";
import { Card } from "./Card";
import styles from "./JobDetail.module.css";
import { DOCUMENTS, RUBRIC_LABELS } from "./labels";
import type { FileEntry, Qa, QaRun } from "./types";

function describe(f: FileEntry): { title: string; open: string } {
  const known = DOCUMENTS.find((d) => d.match.test(f.name));
  return known ?? { title: f.name, open: "Open" };
}

function order(f: FileEntry): number {
  const i = DOCUMENTS.findIndex((d) => d.match.test(f.name));
  return i < 0 ? DOCUMENTS.length : i;
}

function DocRow({ jobId, file }: { jobId: string; file: FileEntry }) {
  const { title, open } = describe(file);
  const when = formatDate(file.modified);
  return (
    <li className={styles.docRow}>
      <FileText size={18} strokeWidth={1.6} aria-hidden="true" className={styles.sec} />
      <div className={styles.grow}>
        <div className={styles.strong}>{title}</div>
        <div className={styles.caption}>
          <span translate="no">{file.name}</span> · {formatBytes(file.size)}
          {when ? ` · ${when}` : ""}
        </div>
      </div>
      <a className={styles.buttonLink} href={fileUrl(jobId, file.name)} target="_blank" rel="noopener noreferrer">
        {open}{" "}
        <span className="sr-only">({file.name}, opens in a new tab)</span>
      </a>
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

function QaSection({ jobId, qa }: { jobId: string; qa: Qa | null }) {
  const toast = useToast();
  const rerun = useRerunQa(jobId);
  const [result, setResult] = useState<QaRun | null>(null);
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
    <div className={styles.qa}>
      <div className={styles.qaHead}>
        <h3 className={styles.h3}>QA</h3>
        <span className={styles.qaVerdict}>
          {verdict}
          {meanText ? <span className={styles.caption}>{meanText}</span> : null}
        </span>
      </div>
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
      {qa?.fail_reasons?.length ? (
        <ul className={styles.bullets}>
          {qa.fail_reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      <div className={styles.buttons}>
        <Button
          size="small"
          {...help("rerunQa")}
          pending={rerun.isPending}
          pendingLabel="Running…"
          onClick={() =>
            rerun.mutate(undefined, {
              onSuccess: (r) => setResult(r),
              onError: (e) => toast.show({ message: errorText(e) }),
            })
          }
        >
          Re-run QA
        </Button>
      </div>
      <div role="status" aria-live="polite">
        {result ? <QaSummary run={result} /> : null}
      </div>
    </div>
  );
}

export function DocumentsCard({
  jobId,
  documents,
  otherFiles = [],
  submitted,
  qa,
}: {
  jobId: string;
  documents: FileEntry[];
  otherFiles?: FileEntry[];
  submitted: string[];
  qa: Qa | null;
}) {
  const toast = useToast();
  const folder = useOpenFolder(jobId);
  const reasonId = useId();
  const docs = documents.toSorted((a, b) => order(a) - order(b) || a.name.localeCompare(b.name));
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
          <DocRow key={f.name} jobId={jobId} file={f} />
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
        <details className={styles.details}>
          <summary>All files ({formatCount(otherFiles.length)})</summary>
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
        </details>
      ) : null}
      <QaSection jobId={jobId} qa={qa} />
    </Card>
  );
}
