import { useId, useState, type FormEvent } from "react";
import { ApiError } from "../../api/client";
import { useUndoSeconds } from "../../api/queries";
import { Button } from "../../kit/Button";
import { SegmentedControl } from "../../kit/SegmentedControl";
import { Sheet } from "../../kit/Sheet";
import { useToast } from "../../kit/Toast";
import { useMarkContact } from "./api";
import styles from "./ContactsPage.module.css";
import type { ContactRow, MarkBody } from "./types";

interface Props {
  contact: ContactRow | null;
  onClose: () => void;
}

/** Record what the candidate's own LinkedIn shows (never scraped): degree and mutual connections. */
export function MarkConnectionSheet({ contact, onClose }: Props) {
  return (
    <Sheet open={contact !== null} onClose={onClose} title="Mark connection" closeLabel="Cancel">
      {contact ? <MarkForm key={`${contact.job_id}/${contact.name}`} contact={contact} onDone={onClose} /> : null}
    </Sheet>
  );
}

function MarkForm({ contact, onDone }: { contact: ContactRow; onDone: () => void }) {
  const hintId = useId();
  const errId = useId();
  const mutualsId = useId();
  const mark = useMarkContact();
  const toast = useToast();
  const undoSeconds = useUndoSeconds();
  const [degree, setDegree] = useState(contact.linkedin_degree ? String(contact.linkedin_degree) : "");
  const [mutuals, setMutuals] = useState(contact.mutuals === null ? "" : String(contact.mutuals));
  const [error, setError] = useState<string | null>(null);

  function body(): MarkBody | string {
    const out: MarkBody = {};
    if (degree && Number(degree) !== contact.linkedin_degree) out.degree = Number(degree);
    const m = mutuals.trim();
    if (m !== "") {
      const n = Number(m);
      if (!Number.isInteger(n) || n < 0) return "Mutual connections must be a whole number, 0 or more.";
      if (n !== contact.mutuals) out.mutuals = n;
    }
    return out;
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const b = body();
    if (typeof b === "string") {
      setError(b);
      document.getElementById(mutualsId)?.focus();
      return;
    }
    if (b.degree === undefined && b.mutuals === undefined) {
      onDone();
      return;
    }
    const prev: MarkBody = {};
    if (b.degree !== undefined && contact.linkedin_degree !== null) prev.degree = contact.linkedin_degree;
    if (b.mutuals !== undefined && contact.mutuals !== null) prev.mutuals = contact.mutuals;
    const canUndo =
      (b.degree === undefined || prev.degree !== undefined) && (b.mutuals === undefined || prev.mutuals !== undefined);
    const target = { jobId: contact.job_id, name: contact.name };
    mark.mutate(
      { ...target, body: b },
      {
        onSuccess: () => {
          onDone();
          toast.show({
            message: `Saved what LinkedIn shows for ${contact.name}.`,
            seconds: undoSeconds,
            onUndo: canUndo ? () => mark.mutate({ ...target, body: prev }) : undefined,
          });
        },
        onError: (err) => setError(err instanceof ApiError ? err.message : "Couldn't save. Try again."),
      },
    );
  }

  return (
    <form className={styles.markForm} onSubmit={onSubmit} aria-describedby={hintId} noValidate>
      <p className={styles.markWho}>
        <strong>{contact.name}</strong>
        {contact.title ? ` · ${contact.title}` : ""}
        {contact.company ? ` · ${contact.company}` : ""}
      </p>
      <p id={hintId} className={styles.markHint}>
        What your own LinkedIn shows. Connected or any mutuals turns automation off for this person; you tailor the
        note yourself.
      </p>
      <div className={styles.field}>
        <span className={styles.fieldLabel} aria-hidden="true">
          Connection
        </span>
        <SegmentedControl label="Connection" value={degree} onValueChange={setDegree}>
          {contact.linkedin_degree === null ? <SegmentedControl.Option value="">Not marked</SegmentedControl.Option> : null}
          <SegmentedControl.Option value="1">1st · connected</SegmentedControl.Option>
          <SegmentedControl.Option value="2">2nd</SegmentedControl.Option>
          <SegmentedControl.Option value="3">3rd</SegmentedControl.Option>
        </SegmentedControl>
      </div>
      <div className={styles.field}>
        <label htmlFor={mutualsId} className={styles.fieldLabel}>
          Mutual connections
        </label>
        <input
          id={mutualsId}
          name="mutuals"
          type="number"
          inputMode="numeric"
          min={0}
          step={1}
          autoComplete="off"
          className={styles.input}
          value={mutuals}
          placeholder={contact.mutuals === null ? "Not marked" : undefined}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errId : undefined}
          onChange={(e) => {
            setMutuals(e.target.value);
            setError(null);
          }}
        />
      </div>
      {error ? (
        <p id={errId} role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
      <div className={styles.markActions}>
        <Button type="submit" variant="primary" pending={mark.isPending} pendingLabel="Saving…">
          Save
        </Button>
      </div>
    </form>
  );
}
