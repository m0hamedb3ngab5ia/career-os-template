import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import styles from "./controls.module.css";

interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** The control that opened it: focus returns here on Escape, and clicks on it don't count as outside. */
  anchorRef: RefObject<HTMLElement | null>;
  label: string;
  className?: string;
  children: ReactNode;
}

/** Non-modal dialog under its anchor (stat tile details). Escape and outside clicks close it. */
export function Popover({ open, onClose, anchorRef, label, className, children }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose();
      anchorRef.current?.focus();
    }
    function onPointer(e: PointerEvent) {
      const t = e.target as Node;
      if (ref.current?.contains(t) || anchorRef.current?.contains(t)) return;
      onClose();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, onClose, anchorRef]);

  if (!open) return null;
  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={label}
      className={className ? `${styles.popover} ${className}` : styles.popover}
    >
      {children}
    </div>
  );
}
