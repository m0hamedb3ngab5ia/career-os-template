import { useEffect, useId, useRef, type ComponentProps, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import styles from "./Sheet.module.css";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface SheetProps {
  open: boolean;
  onClose: () => void;
  /** Visible title in the sheet's bar; also its accessible name. */
  title: string;
  /** Left bar button (HIG: "Close" / "Cancel"). */
  closeLabel?: string;
  /** Optional right bar button, e.g. an Edit action. */
  trailing?: ReactNode;
  children: ReactNode;
  /** Pinned under the scrolling body: the sheet's main actions. */
  footer?: ReactNode;
}

/**
 * Modal sheet (HIG): a bottom sheet on phones, a centred card on wider screens. Focus moves into it and stays
 * there (Tab wraps), Escape or the backdrop closes it, and focus returns to the control that opened it.
 */
export function Sheet({ open, onClose, title, closeLabel = "Close", trailing, children, footer }: SheetProps) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement ? active : null;
    const el = ref.current;
    const first = el?.querySelector<HTMLElement>("[data-autofocus]") ?? el?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? el)?.focus();
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prevOverflow;
      const back = opener.current;
      if (back && back.isConnected) back.focus();
    };
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab") return;
    const items = Array.from(ref.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter(
      (n) => n.getAttribute("aria-hidden") !== "true",
    );
    if (items.length === 0) {
      e.preventDefault();
      return;
    }
    const first = items[0]!;
    const last = items[items.length - 1]!;
    if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return createPortal(
    <div className={styles.layer}>
      <div className={styles.backdrop} aria-hidden="true" onClick={onClose} />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        tabIndex={-1}
        className={styles.sheet}
        onKeyDown={onKeyDown}
      >
        <div className={styles.grabber} aria-hidden="true">
          <span />
        </div>
        <div className={styles.bar}>
          <button type="button" className={styles.barButton} onClick={onClose}>
            {closeLabel}
          </button>
          <h2 id={id} className={styles.title}>
            {title}
          </h2>
          <div className={styles.trailing}>{trailing}</div>
        </div>
        <div className={styles.body}>{children}</div>
        {footer ? <div className={styles.footer}>{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}

/** A text button for the sheet's bar (Edit, Done). Pass `disabled` + `aria-describedby` when it can't act yet. */
export function SheetBarButton(props: ComponentProps<"button">) {
  return <button type="button" {...props} className={styles.barButton} data-strong />;
}
