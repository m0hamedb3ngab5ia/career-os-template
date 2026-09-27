import { Check } from "lucide-react";
import { useRef, useState } from "react";
import type { Meta } from "../../api/meta";
import { Button } from "../../kit/Button";
import { StatusChip } from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { ExternalLink } from "../../kit/ExternalLink";
import { humanize } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { errorText, useMarkSubmitted } from "./api";
import styles from "./JobDetail.module.css";
import { buildSteps, StatusStepper } from "./StatusStepper";
import type { JobDetail } from "./types";

// Statuses where "Mark submitted" makes sense: the job is not applied yet and not closed.
const BEFORE_APPLY = new Set(["found", "scored", "queued", "prepared", "needs_review"]);

export function PostingCard({ jobId, detail, pipeline }: { jobId: string; detail: JobDetail; pipeline?: Meta["pipeline"] }) {
  const toast = useToast();
  const submit = useMarkSubmitted(jobId);
  const [confirming, setConfirming] = useState(false);
  const markRef = useRef<HTMLButtonElement>(null);
  const p = detail.posting;
  const company = p.company || detail.job?.company || jobId;
  const title = p.title || detail.job?.title || "Untitled role";
  const location = [p.location || detail.job?.location, p.remote ? "remote" : null].filter(Boolean).join(" · ");
  const ats = p.ats || detail.job?.ats;
  const atsName = ats ? humanize(ats) : null;
  const url = p.url || detail.job?.url;
  const canSubmit = !!detail.status && BEFORE_APPLY.has(detail.status);

  function cancel() {
    setConfirming(false);
    markRef.current?.focus();
  }

  return (
    <section aria-label="Posting" className={styles.card} data-size="large">
      <div className={styles.posting}>
        <div aria-hidden="true" className={styles.logo}>
          {company.slice(0, 1).toUpperCase()}
        </div>
        <div className={styles.grow}>
          <div className={styles.postingTitle}>
            <h2 className={styles.roleTitle}>{title}</h2>
            {detail.status ? <StatusChip status={detail.status} /> : null}
          </div>
          <div className={styles.postingMeta}>
            <span>{company}</span>
            {location ? <span>{location}</span> : null}
            {atsName ? <span>{atsName}</span> : null}
            {url ? <ExternalLink href={url}>{atsName ? `Open posting on ${atsName}` : "Open posting"}</ExternalLink> : null}
            <span>
              <span className="sr-only">Job ID </span>
              <code translate="no" className={styles.code}>
                {jobId}
              </code>
            </span>
          </div>
        </div>
        {canSubmit ? (
          <Button
            ref={markRef}
            icon={<Check size={14} strokeWidth={1.8} aria-hidden="true" />}
            aria-expanded={confirming}
            onClick={() => setConfirming(true)}
          >
            Mark submitted
          </Button>
        ) : null}
      </div>
      {confirming ? (
        <div className={styles.inlineConfirm}>
          <ConfirmPanel
            question={`Mark ${company} as submitted?`}
            detail="Use this when you sent the application yourself. The status becomes Applied here and in the tracker."
            cancelLabel="Not yet"
            confirmLabel="Mark submitted"
            pending={submit.isPending}
            onCancel={cancel}
            onConfirm={() =>
              submit.mutate(
                {},
                {
                  onSuccess: () => {
                    setConfirming(false);
                    toast.show({ message: `Marked ${company} as submitted` });
                  },
                  onError: (e) => toast.show({ message: errorText(e) }),
                },
              )
            }
          />
        </div>
      ) : null}
      {pipeline ? <StatusStepper steps={buildSteps(detail.status, detail.history, pipeline)} /> : null}
    </section>
  );
}
