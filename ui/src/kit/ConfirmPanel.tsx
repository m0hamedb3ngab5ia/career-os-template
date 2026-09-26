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
  /** Irreversible and destructive (default) or just consequential ("Install the scheduler?"): primary. */
  confirmVariant?: Extract<ButtonVariant, "destructive-filled" | "primary">;
}

/** Inline confirm for irreversible actions. Focus starts on the safe choice; Escape cancels. */
export function ConfirmPanel({
  question,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
  pending,
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
      className={styles.confirm}
      data-variant={confirmVariant}
      onKeyDown={onKeyDown}
    >
      <span id={id} className={styles.confirmQuestion}>
        {question}
      </span>
      <Button ref={cancelRef} size="small" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button size="small" variant={confirmVariant} onClick={onConfirm} pending={pending}>
        {confirmLabel}
      </Button>
    </div>
  );
}
