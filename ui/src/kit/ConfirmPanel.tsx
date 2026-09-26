import { useEffect, useId, useRef, type KeyboardEvent } from "react";
import { Button } from "./Button";
import styles from "./controls.module.css";

interface ConfirmPanelProps {
  /** Say what happens: "Withdraw from Acme? You can’t undo this." */
  question: string;
  /** Optional second line under the question ("Your documents stay in the job folder."). */
  description?: string;
  cancelLabel: string;
  /** Name the outcome on the button ("Withdraw"), never "OK". */
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  pending?: boolean;
}

/** Inline confirm for irreversible actions. Focus starts on the safe choice; Escape cancels. */
export function ConfirmPanel({ question, description, cancelLabel, confirmLabel, onCancel, onConfirm, pending }: ConfirmPanelProps) {
  const id = useId();
  const descId = useId();
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
      aria-describedby={description ? descId : undefined}
      className={styles.confirm}
      onKeyDown={onKeyDown}
    >
      {description ? (
        <span className={styles.confirmQuestion}>
          <span id={id} className={styles.confirmTitle}>
            {question}
          </span>
          <span id={descId} className={styles.confirmDescription}>
            {description}
          </span>
        </span>
      ) : (
        <span id={id} className={styles.confirmQuestion}>
          {question}
        </span>
      )}
      <Button ref={cancelRef} size="small" onClick={onCancel}>
        {cancelLabel}
      </Button>
      <Button size="small" variant="destructive-filled" onClick={onConfirm} pending={pending}>
        {confirmLabel}
      </Button>
    </div>
  );
}
