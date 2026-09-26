import { Copy } from "lucide-react";
import { useId, useState } from "react";
import { Button } from "../../kit/Button";
import { Chip, TierBadge } from "../../kit/chips";
import { ConfirmPanel } from "../../kit/ConfirmPanel";
import { Sheet, SheetBarButton } from "../../kit/Sheet";
import { useToast } from "../../kit/Toast";
import { UnavailableButton } from "../../kit/UnavailableButton";
import { DraftText } from "./DraftText";
import styles from "./DraftSheet.module.css";
import { kindLabel, modeLabel } from "./labels";
import type { Draft } from "./types";

/** An action the sheet offers, or the plain-language reason it can't yet (no backend for it). */
export type SheetAction<T> = T | { unavailable: string };

function isUnavailable<T extends object>(a: SheetAction<T>): a is { unavailable: string } {
  return "unavailable" in a;
}

interface DraftSheetProps {
  open: boolean;
  onClose: () => void;
  draft: Draft | null;
  company?: string | null;
  jobTitle?: string | null;
  tier?: string | null;
  /** Omit for drafts you send yourself (LinkedIn): the sheet then offers Copy text only. */
  approve?: SheetAction<{ label?: string; onApprove: () => void; pending?: boolean }>;
  discard?: SheetAction<{ onDiscard: () => void; onUndo: () => void; after?: string }>;
  edit?: SheetAction<{ onEdit: () => void }>;
  /** Several drafts in one sheet ("Open LinkedIn drafts (3)"). */
  pager?: { index: number; count: number; onPrev: () => void; onNext: () => void };
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function showsLinkedIn(d: Draft): boolean {
  return (d.mode === "linkedin" || d.mode === "manual") && Boolean(d.linkedin_message || d.linkedin_note);
}

function sheetTitle(d: Draft): string {
  return showsLinkedIn(d) ? "LinkedIn draft" : kindLabel(d.kind);
}

function words(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

/** The text a person would send: the email (subject + body), or the LinkedIn message and connection note. */
function sections(d: Draft): { label: string; text: string }[] {
  const out: { label: string; text: string }[] = [];
  if (showsLinkedIn(d)) {
    if (d.linkedin_message) out.push({ label: "Message", text: d.linkedin_message });
    if (d.linkedin_note) out.push({ label: "Connection note", text: d.linkedin_note });
  }
  if (out.length === 0) {
    if (d.subject) out.push({ label: "Subject", text: d.subject });
    out.push({ label: d.subject ? "Body" : "Text", text: d.body });
  }
  return out;
}

/**
 * Review one draft (phone "Approve draft" pattern): who it is for, chips (Draft, N placeholders, how it goes out),
 * the scrollable text with placeholders marked, and Approve / Discard. Approve waits until every placeholder is
 * filled; actions without a backend show why they're off. Nothing here sends.
 */
export function DraftSheet({ open, onClose, draft, company, jobTitle, tier, approve, discard, edit, pager }: DraftSheetProps) {
  const noteId = useId();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [discarded, setDiscarded] = useState(false);

  if (!draft) return null;
  const count = draft.placeholders.length;
  const mode = modeLabel(draft.mode);
  const text = sections(draft);
  const wordCount = words(text.filter((s) => s.label !== "Subject" && s.label !== "Connection note").map((s) => s.text).join(" "));
  const noun = sheetTitle(draft);
  const note =
    count > 0
      ? `Fill ${plural(count, "placeholder", "placeholders")} before approving`
      : approve && isUnavailable(approve)
        ? approve.unavailable
        : null;

  function close() {
    setConfirming(false);
    setDiscarded(false);
    onClose();
  }

  async function copy() {
    const all = text.map((s) => s.text).join("\n\n");
    try {
      await navigator.clipboard.writeText(all);
      toast.show({ message: "Copied. Paste it where you send it." });
    } catch {
      toast.show({ message: "Couldn't copy. Select the text and copy it instead." });
    }
  }

  const editButton =
    edit === undefined ? null : isUnavailable(edit) ? (
      <SheetBarButton aria-disabled="true" title={edit.unavailable} aria-describedby={`${noteId}-edit`}>
        Edit
        <span id={`${noteId}-edit`} className="sr-only">
          {edit.unavailable}
        </span>
      </SheetBarButton>
    ) : (
      <SheetBarButton onClick={edit.onEdit}>Edit</SheetBarButton>
    );

  let approveButton = null;
  if (approve) {
    const label = (!isUnavailable(approve) && approve.label) || `Approve ${noun.toLowerCase()}`;
    approveButton =
      count > 0 ? (
        <Button variant="primary" disabled aria-describedby={noteId} className={styles.big}>
          {label}
        </Button>
      ) : isUnavailable(approve) ? (
        <UnavailableButton variant="primary" reason={approve.unavailable}>
          {label}
        </UnavailableButton>
      ) : (
        <Button variant="primary" className={styles.big} onClick={approve.onApprove} pending={approve.pending} pendingLabel="Approving…">
          {label}
        </Button>
      );
  }

  let discardArea = null;
  if (discard) {
    if (isUnavailable(discard)) {
      discardArea = (
        <UnavailableButton variant="destructive" reason={discard.unavailable}>
          Discard draft
        </UnavailableButton>
      );
    } else if (discarded) {
      discardArea = (
        <div className={styles.discarded} role="status">
          <span>Draft discarded.{discard.after ? ` ${discard.after}` : ""}</span>
          <button
            type="button"
            className={styles.undo}
            onClick={() => {
              discard.onUndo();
              setDiscarded(false);
            }}
          >
            Undo
          </button>
        </div>
      );
    } else if (confirming) {
      discardArea = (
        <ConfirmPanel
          question="Discard this draft?"
          cancelLabel="Keep draft"
          confirmLabel="Discard"
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            discard.onDiscard();
            setConfirming(false);
            setDiscarded(true);
          }}
        />
      );
    } else {
      discardArea = (
        <Button variant="destructive" className={styles.big} onClick={() => setConfirming(true)}>
          Discard draft
        </Button>
      );
    }
  }

  return (
    <Sheet
      open={open}
      onClose={close}
      title={noun}
      trailing={editButton}
      footer={
        <div className={styles.actions}>
          {discardArea}
          {discarded || confirming ? null : approveButton}
          {!approve ? (
            <Button variant="primary" icon={<Copy size={14} aria-hidden="true" />} onClick={copy}>
              Copy text
            </Button>
          ) : null}
        </div>
      }
    >
      <div className={styles.who}>
        {tier ? <TierBadge tier={tier} /> : null}
        {company ? <span className={styles.company}>{company}</span> : null}
        {jobTitle ? <span className={styles.jobTitle}>{jobTitle}</span> : null}
      </div>
      <div className={styles.meta}>
        {draft.contact ? <span>To {draft.contact}</span> : null}
        {draft.to ? (
          <span translate="no" className={styles.address}>
            {draft.to}
          </span>
        ) : null}
        {draft.to && draft.verified ? <Chip tone="green">Verified</Chip> : null}
        <span className="tabular">{plural(wordCount, "word", "words")}</span>
      </div>
      <div className={styles.chips}>
        {draft.sent ? <Chip tone="green">Sent</Chip> : <Chip tone="gray">Draft</Chip>}
        {count > 0 ? <Chip tone="orange">{plural(count, "placeholder", "placeholders")}</Chip> : null}
        <Chip tone={mode.tone}>{mode.label}</Chip>
      </div>
      {text.map((s) => (
        <div key={s.label} className={styles.letterBlock}>
          {text.length > 1 ? <h3 className={styles.letterLabel}>{s.label}</h3> : null}
          <div className={styles.letter} tabIndex={0} role="region" aria-label={`${noun}: ${s.label.toLowerCase()}`}>
            <DraftText text={s.text} />
          </div>
        </div>
      ))}
      {pager && pager.count > 1 ? (
        <div className={styles.pager}>
          <Button size="small" onClick={pager.onPrev} disabled={pager.index === 0}>
            Previous
          </Button>
          <span className="tabular" aria-live="polite">
            {pager.index + 1} of {pager.count}
          </span>
          <Button size="small" onClick={pager.onNext} disabled={pager.index >= pager.count - 1}>
            Next
          </Button>
        </div>
      ) : null}
      <div id={noteId} role="status" aria-live="polite" className={styles.note}>
        {note}
      </div>
    </Sheet>
  );
}
