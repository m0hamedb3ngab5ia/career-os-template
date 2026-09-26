import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "./Button";
import styles from "./inputs.module.css";

interface SheetProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Buttons under the body, right-aligned. */
  footer?: ReactNode;
}

const FOCUSABLE = 'a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea,[tabindex]:not([tabindex="-1"])';

/**
 * A modal sheet (HIG: sheets for previews and confirmations). Focus moves into it, Tab stays inside, Escape or
 * the backdrop closes it, and focus returns to whatever opened it.
 */
export function Sheet({ title, onClose, children, footer }: SheetProps) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
      } else if (e.key === "Tab" && ref.current) {
        const els = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
        if (!els.length) return;
        const first = els[0]!;
        const last = els.at(-1)!;
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={id} className={styles.sheet}>
        <div className={styles.sheetHead}>
          <h2 id={id} className={styles.sheetTitle}>
            {title}
          </h2>
          <Button size="small" onClick={onClose} aria-label="Close" icon={<X size={14} aria-hidden="true" />}>
            <span className="sr-only">Close</span>
          </Button>
        </div>
        <div className={styles.sheetBody}>{children}</div>
        {footer ? <div className={styles.sheetHead}>{footer}</div> : null}
      </div>
    </div>
  );
}
