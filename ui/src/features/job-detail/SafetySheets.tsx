import { useId, useRef, useState, type FormEvent } from "react";
import { Button } from "../../kit/Button";
import { Sheet } from "../../kit/Dialog";
import { useToast } from "../../kit/Toast";
import { errorText, useFlagCompany, useVerifyCompany } from "./api";
import { lines } from "./Evidence";
import styles from "./JobDetail.module.css";

interface SheetProps {
  jobId: string;
  company: string;
  open: boolean;
  onClose: () => void;
}

function Radios({
  legend,
  name,
  value,
  options,
  onChange,
}: {
  legend: string;
  name: string;
  value: string;
  options: { value: string; label: string; hint?: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.label}>{legend}</legend>
      {options.map((o) => (
        <label key={o.value} className={styles.radio}>
          <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} />
          <span>
            {o.label}
            {o.hint ? <span className={styles.hint}> {o.hint}</span> : null}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: (ids: { id: string; describedBy?: string }) => React.ReactNode;
}) {
  const id = useId();
  const hintId = useId();
  const errId = useId();
  const describedBy = [hint ? hintId : null, error ? errId : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      {children({ id, describedBy })}
      {hint ? (
        <span id={hintId} className={styles.hint}>
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={errId} className={styles.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

/** Verify company → POST safety/verify. Low risk needs two or more signals (the server enforces it too). */
export function VerifySheet({ jobId, company, open, onClose }: SheetProps) {
  const toast = useToast();
  const verify = useVerifyCompany(jobId);
  const formId = useId();
  const signalsRef = useRef<HTMLTextAreaElement>(null);
  const [risk, setRisk] = useState("low");
  const [signals, setSignals] = useState("");
  const [evidence, setEvidence] = useState("");
  const [domain, setDomain] = useState("");
  const [error, setError] = useState<string>();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const list = lines(signals);
    if (risk === "low" && list.length < 2) {
      setError("Low risk needs at least two signals.");
      signalsRef.current?.focus();
      return;
    }
    setError(undefined);
    const ev = lines(evidence);
    verify.mutate(
      { risk, signals: list, ...(ev.length ? { evidence: ev } : {}), ...(domain.trim() ? { domain: domain.trim() } : {}) },
      {
        onSuccess: () => {
          toast.show({ message: `Marked ${company} as verified (${risk} risk)` });
          onClose();
        },
        onError: (err) => toast.show({ message: errorText(err) }),
      },
    );
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={`Verify ${company}`}
      description="Record why this company is real. Verified companies skip the company check on future postings."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" form={formId} pending={verify.isPending} pendingLabel="Saving…">
            Save verification
          </Button>
        </>
      }
    >
      <form id={formId} className={styles.form} onSubmit={onSubmit} noValidate>
        <Radios
          legend="Risk"
          name="risk"
          value={risk}
          onChange={setRisk}
          options={[
            { value: "low", label: "Low", hint: "(needs two or more signals)" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
          ]}
        />
        <Field label="Signals" hint="One per line, e.g. “Careers page lists this role”." error={error}>
          {({ id, describedBy }) => (
            <textarea
              ref={signalsRef}
              id={id}
              name="signals"
              rows={4}
              autoComplete="off"
              className={styles.input}
              aria-describedby={describedBy}
              aria-invalid={error ? true : undefined}
              value={signals}
              onChange={(e) => setSignals(e.target.value)}
            />
          )}
        </Field>
        <Field label="Evidence links (optional)" hint="One URL per line.">
          {({ id, describedBy }) => (
            <textarea
              id={id}
              name="evidence"
              rows={3}
              autoComplete="off"
              className={styles.input}
              aria-describedby={describedBy}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          )}
        </Field>
        <Field label="Domain (optional)">
          {({ id }) => (
            <input
              id={id}
              name="domain"
              type="text"
              inputMode="url"
              autoComplete="off"
              spellCheck={false}
              className={styles.input}
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
          )}
        </Field>
      </form>
    </Sheet>
  );
}

/** Flag as suspicious → POST safety/flag. */
export function FlagSheet({ jobId, company, open, onClose }: SheetProps) {
  const toast = useToast();
  const flag = useFlagCompany(jobId);
  const formId = useId();
  const [reason, setReason] = useState("");
  const [confidence, setConfidence] = useState("medium");
  const [evidence, setEvidence] = useState("");
  const [notes, setNotes] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const ev = lines(evidence);
    flag.mutate(
      {
        confidence,
        ...(reason.trim() ? { reason: reason.trim() } : {}),
        ...(ev.length ? { evidence: ev } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      },
      {
        onSuccess: () => {
          toast.show({ message: `Flagged ${company} as suspicious` });
          onClose();
        },
        onError: (err) => toast.show({ message: errorText(err) }),
      },
    );
  }

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={`Flag ${company} as suspicious`}
      description="Flagged companies are blocked or sent for review on every posting until you clear the flag."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="destructive-filled" type="submit" form={formId} pending={flag.isPending} pendingLabel="Saving…">
            Flag company
          </Button>
        </>
      }
    >
      <form id={formId} className={styles.form} onSubmit={onSubmit}>
        <Field label="Reason">
          {({ id }) => (
            <textarea
              id={id}
              name="reason"
              rows={3}
              autoComplete="off"
              className={styles.input}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </Field>
        <Radios
          legend="Confidence"
          name="confidence"
          value={confidence}
          onChange={setConfidence}
          options={[
            { value: "high", label: "High", hint: "(blocks the job)" },
            { value: "medium", label: "Medium", hint: "(asks for review)" },
          ]}
        />
        <Field label="Evidence links (optional)" hint="One URL per line.">
          {({ id, describedBy }) => (
            <textarea
              id={id}
              name="evidence"
              rows={3}
              autoComplete="off"
              className={styles.input}
              aria-describedby={describedBy}
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
            />
          )}
        </Field>
        <Field label="Notes (optional)">
          {({ id }) => (
            <textarea
              id={id}
              name="notes"
              rows={2}
              autoComplete="off"
              className={styles.input}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          )}
        </Field>
      </form>
    </Sheet>
  );
}
