import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import styles from "./menus.module.css";

interface SheetProps {
  title: string;
  /** One line under the title saying what the sheet is for. */
  description?: string;
  onClose: () => void;
  children: ReactNode;
  /** Buttons row (Cancel, then the action). */
  footer?: ReactNode;
}

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A modal sheet for edits (HIG: sheets, not alerts). Focus moves to the first field, stays inside while open
 * (Tab wraps), Escape or the backdrop closes it, and focus returns to whatever opened it.
 */
export function Sheet({ title, description, onClose, children, footer }: SheetProps) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = ref.current?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? ref.current)?.focus();
    return () => opener?.focus();
  }, []);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== "Tab" || !ref.current) return;
    const all = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (!all.length) return;
    const first = all[0]!;
    const last = all.at(-1)!;
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  return (
    <div className={styles.backdrop} onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${id}-title`}
        aria-describedby={description ? `${id}-desc` : undefined}
        tabIndex={-1}
        className={styles.sheet}
        onKeyDown={onKeyDown}
      >
        <h2 id={`${id}-title`} className={styles.sheetTitle}>
          {title}
        </h2>
        {description ? (
          <p id={`${id}-desc`} className={styles.sheetDesc}>
            {description}
          </p>
        ) : null}
        <div className={styles.sheetBody}>{children}</div>
        {footer ? <div className={styles.sheetFooter}>{footer}</div> : null}
      </div>
    </div>
  );
}
