import { useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { ApiError } from "../../api/client";
import { useMeta } from "../../api/meta";
import { Page } from "../../app/PageHeader";
import { Button } from "../../kit/Button";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { EmptyState } from "../../kit/EmptyState";
import { STATUSES, describeCode } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { ActivityCard } from "./ActivityCard";
import { errorText, useJob, useSetStatus, useWithdraw } from "./api";
import { ApplySessionCard } from "./ApplySessionCard";
import { ContactsCard } from "./ContactsCard";
import { DocumentsCard } from "./DocumentsCard";
import { OverrideMenu, StatusMenu, WithdrawButton } from "./HeaderActions";
import styles from "./JobDetail.module.css";
import { PipelineCard } from "./PipelineCard";
import { PostingCard } from "./PostingCard";
import { SafetyCard } from "./SafetyCard";
import { ScoreCard } from "./ScoreCard";
import type { JobDetail } from "./types";

const CLOSED_FOR_WITHDRAW = new Set(["withdrawn", "rejected", "ghosted", "skipped", "offer"]);

function Breadcrumb({ company }: { company: string }) {
  return (
    <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
      <Link to="/jobs">Jobs</Link> <span aria-hidden="true">›</span> <span aria-current="page">{company}</span>
    </nav>
  );
}

function Detail({ jobId, detail }: { jobId: string; detail: JobDetail }) {
  const toast = useToast();
  const meta = useMeta();
  const withdraw = useWithdraw(jobId);
  const restore = useSetStatus(jobId);
  const [confirmWithdraw, setConfirmWithdraw] = useState(false);
  const withdrawRef = useRef<HTMLButtonElement>(null);

  const company = detail.posting.company || detail.job?.company || jobId;
  const tier = detail.score?.tier ?? detail.job?.tier ?? null;
  const statusLabel = detail.status ? describeCode(STATUSES, detail.status).label : null;
  const canWithdraw = !detail.status || !CLOSED_FOR_WITHDRAW.has(detail.status);

  function cancelWithdraw() {
    setConfirmWithdraw(false);
    withdrawRef.current?.focus();
  }

  function doWithdraw() {
    withdraw.mutate(
      {},
      {
        onSuccess: (r) => {
          setConfirmWithdraw(false);
          toast.show({
            message: "Application withdrawn",
            seconds: meta.data?.ui?.undo_seconds,
            onUndo: r.previous
              ? () =>
                  restore.mutate(
                    { status: r.previous!, note: "undo withdraw" },
                    { onError: (e) => toast.show({ message: errorText(e) }) },
                  )
              : undefined,
          });
        },
        onError: (e) => toast.show({ message: errorText(e) }),
      },
    );
  }

  const subtitle = (
    <span className={styles.subtitle}>
      <Breadcrumb company={company} />
      {[tier ? `Tier ${tier}` : null, statusLabel].filter(Boolean).map((t) => (
        <span key={t}>· {t}</span>
      ))}
    </span>
  );

  return (
    <Page
      title={company}
      subtitle={subtitle}
      actions={
        <>
          <StatusMenu jobId={jobId} status={detail.status} />
          <OverrideMenu jobId={jobId} override={detail.override} />
          {canWithdraw ? (
            <WithdrawButton ref={withdrawRef} expanded={confirmWithdraw} onClick={() => setConfirmWithdraw(true)} />
          ) : null}
        </>
      }
    >
      <div className={styles.stack}>
        {confirmWithdraw ? (
          <ConfirmPanel
            question={`Withdraw from ${company}?`}
            detail="career-os stops all work on this job. Your documents stay in the job folder."
            cancelLabel="Keep application"
            confirmLabel="Withdraw"
            pending={withdraw.isPending}
            onCancel={cancelWithdraw}
            onConfirm={doWithdraw}
          />
        ) : null}
        <PipelineCard jobId={jobId} />
        <PostingCard jobId={jobId} detail={detail} pipeline={meta.data?.pipeline} />
        <div className={styles.grid}>
          <div className={styles.column}>
            <SafetyCard
              jobId={jobId}
              company={company}
              tier={tier}
              safety={detail.safety}
              registry={detail.registry}
            />
            <ScoreCard score={detail.score} />
          </div>
          <div className={styles.column}>
            <DocumentsCard
              jobId={jobId}
              documents={detail.documents}
              otherFiles={detail.other_files}
              submitted={detail.submitted}
              qa={detail.qa}
            />
            <ContactsCard
              contacts={detail.contacts}
              policy={detail.contacts_policy ?? []}
              outreach={detail.outreach}
            />
          </div>
          <div className={styles.column}>
            <ApplySessionCard jobId={jobId} session={detail.apply_session} screenshots={detail.screenshots} />
            <ActivityCard activity={detail.activity ?? []} history={detail.history} />
          </div>
        </div>
      </div>
    </Page>
  );
}

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);

  if (job.isPending) {
    return (
      <Page busy title="Job" subtitle={<Breadcrumb company="Loading…" />}>
        <p className={styles.muted}>Loading job…</p>
      </Page>
    );
  }
  if (job.isError) {
    const missing = job.error instanceof ApiError && job.error.status === 404;
    return (
      <Page title={missing ? "Job not found" : "Couldn’t load this job"}>
        <EmptyState
          title={missing ? "No job with this ID" : "Something went wrong"}
          action={
            missing ? (
              <Link to="/jobs">Back to Jobs</Link>
            ) : (
              <Button size="small" onClick={() => void job.refetch()}>
                Try again
              </Button>
            )
          }
        >
          {missing ? "It may have been pruned, or the link is mistyped." : errorText(job.error)}
        </EmptyState>
      </Page>
    );
  }
  return <Detail jobId={jobId} detail={job.data} />;
}
