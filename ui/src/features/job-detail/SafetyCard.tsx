import { ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip, SafetyChip } from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { Dialog } from "../../kit/Dialog";
import { describeCode } from "../../kit/labels";
import { useToast } from "../../kit/Toast";
import { formatCount, formatDate } from "../../lib/format";
import { errorText, useClearFlag } from "./api";
import { Card, Muted } from "./Card";
import { EvidenceList } from "./Evidence";
import styles from "./JobDetail.module.css";
import { FLAG_LEVELS, flagLabel } from "./labels";
import { FlagSheet, VerifySheet } from "./SafetySheets";
import type { Registry, Safety, SafetyFlag } from "./types";

interface Props {
  jobId: string;
  company: string;
  tier: string | null | undefined;
  safety: Safety | null;
  registry: Registry | undefined;
}

function FlagRow({ flag, onEvidence }: { flag: SafetyFlag; onEvidence: () => void }) {
  const label = flagLabel(flag.code);
  const level = describeCode(FLAG_LEVELS, flag.level);
  const when = formatDate(flag.at);
  return (
    <li className={styles.flag}>
      <div className={styles.flagText}>
        <div className={styles.strong}>{label}</div>
        {flag.detail ? <div>{flag.detail}</div> : null}
        <div className={styles.ter}>
          {level.label}
          {when ? ` · ${when}` : ""} ·{" "}
          <code translate="no" className={styles.code}>
            {flag.code}
          </code>
        </div>
      </div>
      {flag.evidence?.length ? (
        <button type="button" className={styles.linkButton} aria-haspopup="dialog" onClick={onEvidence}>
          Evidence <span className="sr-only">for {label.toLowerCase()}</span>
        </button>
      ) : null}
    </li>
  );
}

function runsCount(runs: Safety["runs"]): number | null {
  if (typeof runs === "number") return runs;
  return Array.isArray(runs) ? runs.length : null;
}

export function SafetyCard({ jobId, company, tier, safety, registry }: Props) {
  const toast = useToast();
  const clear = useClearFlag(jobId);
  const [evidenceFor, setEvidenceFor] = useState<SafetyFlag | null>(null);
  const [sheet, setSheet] = useState<"verify" | "flag" | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const clearRef = useRef<HTMLButtonElement>(null);
  const flags = safety?.flags ?? [];
  const flagged = registry?.flagged && (registry.flagged.state ?? "active") === "active" ? registry.flagged : null;
  const verified = registry?.verified ?? null;
  const runs = runsCount(safety?.runs);

  function closeClear() {
    setConfirmClear(false);
    clearRef.current?.focus();
  }

  return (
    <Card
      title="Safety"
      icon={<ShieldCheck size={16} strokeWidth={1.7} aria-hidden="true" />}
      aside={safety ? <SafetyChip verdict={safety.verdict} /> : <Chip tone="gray">Not checked</Chip>}
    >
      {tier === "A" ? <Muted>Auto-submit blocked: Tier A is always you-submit.</Muted> : null}
      {verified ? (
        <Muted>
          Verified company: {verified.risk} risk · {formatCount(verified.signals.length)} signals
          {verified.checked_at ? ` · ${formatDate(verified.checked_at)}` : ""}
        </Muted>
      ) : null}
      {flagged ? (
        <p className={styles.alert}>
          Flagged as suspicious{flagged.reason ? `: ${flagged.reason}` : ""}
          {flagged.confidence ? ` · ${flagged.confidence} confidence` : ""}
        </p>
      ) : null}
      {flags.length ? (
        <ul className={styles.list}>
          {flags.map((f, i) => (
            <FlagRow key={`${f.code}-${i}`} flag={f} onEvidence={() => setEvidenceFor(f)} />
          ))}
        </ul>
      ) : safety ? (
        <Muted>No flags on this posting.</Muted>
      ) : (
        <Muted>The safety check runs when the job is scored.</Muted>
      )}
      <div className={styles.buttons}>
        <Button size="small" onClick={() => setSheet("verify")} aria-haspopup="dialog">
          Verify company
        </Button>
        <Button size="small" onClick={() => setSheet("flag")} aria-haspopup="dialog">
          Flag as suspicious
        </Button>
        {flagged ? (
          <Button
            ref={clearRef}
            size="small"
            variant="destructive"
            aria-expanded={confirmClear}
            onClick={() => setConfirmClear(true)}
          >
            Clear flag…
          </Button>
        ) : null}
        {runs ? <span className={styles.caption}>Checked {formatCount(runs)} times</span> : null}
      </div>
      {confirmClear ? (
        <ConfirmPanel
          question={`Clear the flag on ${company}?`}
          description="Its postings stop being blocked or sent for review."
          cancelLabel="Keep flag"
          confirmLabel="Clear flag"
          pending={clear.isPending}
          onCancel={closeClear}
          onConfirm={() =>
            clear.mutate(
              {},
              {
                onSuccess: () => {
                  setConfirmClear(false);
                  toast.show({ message: `Cleared the flag on ${company}` });
                },
                onError: (e) => toast.show({ message: errorText(e) }),
              },
            )
          }
        />
      ) : null}
      <Dialog
        open={evidenceFor !== null}
        onClose={() => setEvidenceFor(null)}
        title={evidenceFor ? `Evidence: ${flagLabel(evidenceFor.code)}` : "Evidence"}
        description={evidenceFor?.detail}
      >
        <EvidenceList items={evidenceFor?.evidence ?? []} />
      </Dialog>
      <VerifySheet jobId={jobId} company={company} open={sheet === "verify"} onClose={() => setSheet(null)} />
      <FlagSheet jobId={jobId} company={company} open={sheet === "flag"} onClose={() => setSheet(null)} />
    </Card>
  );
}
