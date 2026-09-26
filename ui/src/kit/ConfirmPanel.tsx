import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import { Button, type ButtonVariant } from "./Button";
import styles from "./controls.module.css";

interface ConfirmPanelProps {
  /** Say what happens: "Withdraw from Acme? You can’t undo this." */
  question: string;
  cancelLabel: string;
  /** Name the outcome on the button ("Withdraw"), never "OK". */
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  pending?: boolean;
  /** A second line under the question: what happens next and how to undo it. */
  detail?: string;
  /** "primary" for a reversible confirm (blue on a neutral panel); destructive red is the default. */
  confirmVariant?: Extract<ButtonVariant, "primary" | "destructive-filled">;
}

/** Inline confirm for irreversible actions. Focus starts on the safe choice; Escape cancels. */
export function ConfirmPanel({
  question,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
  pending,
  detail,
  confirmVariant = "destructive-filled",
}: ConfirmPanelProps) {
  const id = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => cancelRef.current?.focus(), []);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    }
  }

  return (
    <div
      role="alertdialog"
      aria-labelledby={id}
      aria-describedby={detail ? `${id}-detail` : undefined}
      className={styles.confirm}
      data-variant={confirmVariant}
      data-stacked={detail ? true : undefined}
      onKeyDown={onKeyDown}
    >
      <span id={id} className={styles.confirmQuestion}>
        {question}
      </span>
      {detail ? (
        <span id={`${id}-detail`} className={styles.confirmDetail}>
          {detail}
        </span>
      ) : null}
      <span className={styles.confirmButtons}>
        <Button ref={cancelRef} size="small" onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button size="small" variant={confirmVariant} onClick={onConfirm} pending={pending}>
          {confirmLabel}
        </Button>
      </span>
    </div>
  );
}
