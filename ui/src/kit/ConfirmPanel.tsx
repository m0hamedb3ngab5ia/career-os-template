import { useEffect, useId, useLayoutEffect, useRef, type KeyboardEvent, type RefObject } from "react";
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
  /** The control that opened the panel. When the panel closes (Cancel, Escape, or after confirming) and focus
   * would otherwise fall to the page, it goes back here; the trigger may re-mount as the panel closes. */
  returnFocusRef?: RefObject<HTMLElement | null>;
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
  returnFocusRef,
}: ConfirmPanelProps) {
  const id = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const hadFocus = useRef(false);
  useEffect(() => cancelRef.current?.focus(), []);
  // The layout cleanup runs while the panel is still in the DOM: note whether it holds focus. The passive
  // cleanup runs after the commit that removed it, so a trigger that re-mounted in that commit already has
  // its ref. Focus only moves if it was inside the panel and has now fallen to <body>.
  useLayoutEffect(
    () => () => {
      hadFocus.current = Boolean(panelRef.current?.contains(document.activeElement));
    },
    [],
  );
  useEffect(() => {
    const ref = returnFocusRef;
    return () => {
      const active = document.activeElement;
      if (hadFocus.current && (!active || active === document.body)) ref?.current?.focus();
    };
  }, [returnFocusRef]);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    }
  }

  return (
    <div
      ref={panelRef}
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
      <Button size="small" variant={confirmVariant} onClick={onConfirm} pending={pending} pendingLabel={`${confirmLabel}…`}>
        {confirmLabel}
      </Button>
    </div>
  );
}
